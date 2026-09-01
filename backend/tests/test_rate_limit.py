"""Auth rate limiting. The rest of the suite runs with it disabled (see
conftest); this module turns it on explicitly."""

import pytest

from app.config import get_settings
from app.core.rate_limit import login_limiter


@pytest.fixture()
def rate_limited(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
    get_settings.cache_clear()
    login_limiter.reset()
    yield
    login_limiter.reset()
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "false")
    get_settings.cache_clear()


def test_repeated_failed_logins_are_throttled(client, rate_limited):
    client.post(
        "/auth/signup",
        json={"org_name": "Brute EM", "org_slug": "brute-em", "email": "owner@brute.example.com", "password": "supersecret1"},
    )

    statuses = [
        client.post("/auth/login", data={"username": "owner@brute.example.com", "password": "wrong-password"}).status_code
        for _ in range(login_limiter.max_requests + 3)
    ]

    assert statuses[0] == 401, "the first few attempts should just fail normally"
    assert 429 in statuses, "sustained guessing should eventually be throttled"

    throttled = client.post(
        "/auth/login", data={"username": "owner@brute.example.com", "password": "supersecret1"}
    )
    assert throttled.status_code == 429
    assert throttled.headers.get("Retry-After")


def test_limiter_is_off_when_disabled(client):
    """Default suite config: many logins in a row, no throttling."""
    client.post(
        "/auth/signup",
        json={"org_name": "Open EM", "org_slug": "open-em", "email": "owner@open.example.com", "password": "supersecret1"},
    )
    for _ in range(25):
        resp = client.post("/auth/login", data={"username": "owner@open.example.com", "password": "supersecret1"})
        assert resp.status_code == 200
