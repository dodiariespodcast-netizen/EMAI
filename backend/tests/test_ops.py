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


def test_unhandled_errors_return_a_traceable_envelope():
    """A crash must not leak a stack trace to the caller, but must hand back
    the id that identifies it in the logs.

    Built on its own app rather than by appending a route to the real one:
    the real app mounts the SPA catch-all last, so anything registered after
    it would never be reached.
    """
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.core.observability import install as install_observability

    app = FastAPI()
    install_observability(app)

    @app.get("/boom")
    def boom():
        raise RuntimeError("simulated failure")

    with TestClient(app, raise_server_exceptions=False) as client:
        resp = client.get("/boom")

    assert resp.status_code == 500
    body = resp.json()
    assert body["request_id"]
    assert resp.headers["X-Request-ID"] == body["request_id"]
    assert "simulated failure" not in resp.text
