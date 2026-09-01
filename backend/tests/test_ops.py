"""Health probes and request-id plumbing -- the bits a deployment depends on."""


def test_liveness_and_readiness(client):
    live = client.get("/health")
    assert live.status_code == 200
    assert live.json()["status"] == "ok"
    assert live.json()["version"]

    ready = client.get("/health/ready")
    assert ready.status_code == 200
    assert ready.json()["status"] == "ready"


def test_every_response_carries_a_request_id(client):
    resp = client.get("/health")
    assert resp.headers.get("X-Request-ID")

    # A supplied id is echoed back, so a caller can correlate its own logs.
    supplied = client.get("/health", headers={"X-Request-ID": "trace-me-123"})
    assert supplied.headers["X-Request-ID"] == "trace-me-123"


def test_unhandled_errors_return_a_traceable_envelope(client):
    """A crash must not leak a stack trace to the caller, but must hand back
    the id that identifies it in the logs."""
    from app.main import app

    @app.get("/_test_boom")
    def boom():
        raise RuntimeError("simulated failure")

    try:
        resp = client.get("/_test_boom")
        assert resp.status_code == 500
        body = resp.json()
        assert body["request_id"]
        assert "simulated failure" not in resp.text
    finally:
        app.router.routes = [r for r in app.router.routes if getattr(r, "path", None) != "/_test_boom"]
