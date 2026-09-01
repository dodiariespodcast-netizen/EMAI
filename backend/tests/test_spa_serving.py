"""Serving the built frontend from the API process.

This is what the single-container deployment depends on, so it's tested
against a throwaway build directory rather than whatever happens to be in
frontend/dist -- these pass whether or not the frontend has been built.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.spa import mount_frontend, resolve_static_dir


@pytest.fixture()
def spa_client(tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>App shell</title>")
    (dist / "assets" / "index-abc123.js").write_text("console.log('bundle')")

    app = FastAPI()

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/physicians")
    def physicians():
        return [{"id": "p1"}]

    mount_frontend(app, str(dist))
    return TestClient(app)


def test_api_routes_still_win_over_the_static_mount(spa_client):
    assert spa_client.get("/health").json() == {"status": "ok"}
    assert spa_client.get("/physicians").json() == [{"id": "p1"}]


def test_root_serves_the_app_shell(spa_client):
    resp = spa_client.get("/")
    assert resp.status_code == 200
    assert "App shell" in resp.text


def test_client_side_routes_fall_back_to_the_shell(spa_client):
    """A deep link like /app/schedule is a route inside the SPA, not a file."""
    resp = spa_client.get("/app/schedule", headers={"Accept": "text/html"})
    assert resp.status_code == 200
    assert "App shell" in resp.text


def test_unknown_api_path_still_404s_for_json_clients(spa_client):
    """The SPA fallback must not turn a mistyped endpoint into a page of HTML."""
    resp = spa_client.get("/definitely-not-a-route", headers={"Accept": "application/json"})
    assert resp.status_code == 404
    assert "App shell" not in resp.text


def test_cache_headers(spa_client):
    """Hashed assets cache forever; the shell must not, or a deploy leaves
    browsers asking for bundle files that no longer exist."""
    asset = spa_client.get("/assets/index-abc123.js")
    assert asset.status_code == 200
    assert "immutable" in asset.headers["cache-control"]

    shell = spa_client.get("/")
    assert shell.headers["cache-control"] == "no-cache"


def test_no_frontend_build_leaves_a_working_api(tmp_path):
    """Running as a plain API (frontend hosted elsewhere) must still work."""
    app = FastAPI()

    @app.get("/health")
    def health():
        return {"status": "ok"}

    assert mount_frontend(app, str(tmp_path / "does-not-exist")) is None

    client = TestClient(app)
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/").status_code == 404


def test_static_dir_without_an_index_is_ignored(tmp_path):
    """A misconfigured STATIC_DIR shouldn't take the API down with it."""
    (tmp_path / "empty").mkdir()
    assert resolve_static_dir(str(tmp_path / "empty")) is None
