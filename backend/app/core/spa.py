"""Serving the built frontend from the API process.

This is what makes a single-container deployment possible: one service, one
URL, no CORS configuration, and no build-time API URL baked into the bundle
(the frontend falls back to its own origin). Splitting the frontend onto a
CDN/static host is still supported -- just don't set STATIC_DIR.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

logger = logging.getLogger("emai.spa")


class SpaStaticFiles(StaticFiles):
    """Static files with client-side-routing fallback.

    A request for /app/schedule is a route inside the SPA, not a file, so an
    unmatched path returns index.html instead of 404 -- but only for clients
    that asked for HTML. An API client hitting a mistyped endpoint still gets
    a real 404 rather than a page of HTML.
    """

    async def get_response(self, path: str, scope: Scope) -> Response:
        try:
            response = await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code != 404 or not _wants_html(scope):
                raise
            response = await super().get_response("index.html", scope)

        # Asset filenames are content-hashed, so they can cache forever;
        # index.html must not, or a deploy leaves browsers pointing at
        # bundle files that no longer exist.
        if path.startswith("assets/"):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        else:
            response.headers["Cache-Control"] = "no-cache"
        return response


def _wants_html(scope: Scope) -> bool:
    for key, value in scope.get("headers", []):
        if key == b"accept":
            return b"text/html" in value or b"*/*" == value.strip()
    return False


def resolve_static_dir(configured: str | None) -> Path | None:
    """Where the built frontend lives, if anywhere.

    An explicit STATIC_DIR wins. Otherwise look for the sibling
    `frontend/dist`, so `npm run build` + `uvicorn` locally exercises the
    same single-origin setup that gets deployed.
    """
    if configured:
        path = Path(configured).expanduser().resolve()
        if not (path / "index.html").is_file():
            logger.warning("STATIC_DIR=%s has no index.html; not serving a frontend", path)
            return None
        return path

    sibling = Path(__file__).resolve().parents[3] / "frontend" / "dist"
    return sibling if (sibling / "index.html").is_file() else None


def mount_frontend(app: FastAPI, configured: str | None) -> Path | None:
    """Mounts the SPA at / if a build is available. Must be called AFTER every
    API router is registered, since Starlette matches routes in order and this
    mount would otherwise shadow them."""
    static_dir = resolve_static_dir(configured)
    if static_dir is None:
        logger.info("No frontend build found; serving the API only")
        return None

    app.mount("/", SpaStaticFiles(directory=str(static_dir), html=True), name="spa")
    logger.info("Serving frontend from %s", static_dir)
    return static_dir
