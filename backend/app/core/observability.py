"""Request logging and a catch-all error handler.

Every request gets an id that shows up in the log line and in the response
headers/error body, so a customer saying "it broke at 2:41" can be traced to
one specific request without guesswork.
"""

from __future__ import annotations

import logging
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger("emai.request")


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def install(app: FastAPI) -> None:
    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
        request.state.request_id = request_id
        started = time.monotonic()
        try:
            response = await call_next(request)
        except Exception:
            elapsed_ms = (time.monotonic() - started) * 1000
            logger.exception(
                "request_failed id=%s %s %s %.1fms", request_id, request.method, request.url.path, elapsed_ms
            )
            return JSONResponse(
                status_code=500,
                content={
                    "detail": "Something went wrong on our end. Quote this id if you get in touch.",
                    "request_id": request_id,
                },
                headers={"X-Request-ID": request_id},
            )

        elapsed_ms = (time.monotonic() - started) * 1000
        # Health checks fire constantly; logging them buries everything else.
        if request.url.path not in ("/health", "/health/ready"):
            logger.info(
                "id=%s %s %s -> %s %.1fms",
                request_id,
                request.method,
                request.url.path,
                response.status_code,
                elapsed_ms,
            )
        response.headers["X-Request-ID"] = request_id
        return response
