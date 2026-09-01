"""Fixed-window rate limiting for the endpoints worth brute-forcing.

Deliberately in-process: it needs no extra infrastructure and stops the
attack that actually matters (credential stuffing against a single API
instance). Behind more than one worker/replica the effective limit is
per-process, so a production deployment that scales out should move this to
Redis -- the interface here is small enough to swap.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status


class RateLimiter:
    def __init__(self, max_requests: int, window_seconds: int) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str) -> int | None:
        """Records a hit. Returns None if allowed, or the seconds to wait."""
        now = time.monotonic()
        cutoff = now - self.window_seconds
        with self._lock:
            hits = self._hits[key]
            while hits and hits[0] < cutoff:
                hits.popleft()
            if len(hits) >= self.max_requests:
                return max(1, int(hits[0] + self.window_seconds - now))
            hits.append(now)
            return None

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


def client_key(request: Request) -> str:
    """Client identity for limiting. Honors X-Forwarded-For because these
    deployments sit behind a proxy/load balancer; only the first hop is used."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# Sign-in and password-reset endpoints: tight, since these are the ones an
# attacker hammers. Generous enough that a person fat-fingering a password a
# few times never notices.
login_limiter = RateLimiter(max_requests=10, window_seconds=60)
# Anything that sends an email on demand, to keep the app from being used as
# a spam cannon.
email_limiter = RateLimiter(max_requests=5, window_seconds=300)


def _enforce(limiter: RateLimiter, request: Request) -> None:
    from app.config import get_settings

    if not get_settings().rate_limit_enabled:
        return
    retry_after = limiter.check(client_key(request))
    if retry_after is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many attempts. Try again shortly.",
            headers={"Retry-After": str(retry_after)},
        )


def limit_login(request: Request) -> None:
    _enforce(login_limiter, request)


def limit_email(request: Request) -> None:
    _enforce(email_limiter, request)
