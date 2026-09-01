"""Verifies "Sign in with ___" ID tokens (Google, Microsoft) so the
frontend can authenticate users via each provider's client-side SDK
(Google Identity Services / MSAL) without us ever handling passwords for
those accounts, and without running a server-side OAuth code exchange.

The frontend gets a signed ID token from the provider and POSTs it to us;
we verify its signature against the provider's published JWKS, check
audience/issuer, and trust the email claim inside. Both providers are
handled through the same code path so adding a third ("other emails" --
e.g. Okta, a hospital's own IdP) is a config entry, not new logic.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import httpx
from jose import jwt
from jose.exceptions import JWTError

from app.config import get_settings

_PROVIDERS: dict[str, dict] = {
    "google": {
        "issuers": ("https://accounts.google.com", "accounts.google.com"),
        "jwks_uri": "https://www.googleapis.com/oauth2/v3/certs",
        "client_id_setting": "google_client_id",
    },
    "microsoft": {
        # Multi-tenant Microsoft issuers are per-tenant
        # ("https://login.microsoftonline.com/<tenant>/v2.0"); we validate the
        # prefix rather than an exact match.
        "issuer_prefix": "https://login.microsoftonline.com/",
        "jwks_uri": "https://login.microsoftonline.com/common/discovery/v2.0/keys",
        "client_id_setting": "microsoft_client_id",
    },
}

_JWKS_TTL_SECONDS = 3600
_jwks_cache: dict[str, tuple[float, dict]] = {}


class OAuthVerificationError(Exception):
    """Raised for any bad/forged/misconfigured token; callers turn this
    into a 400/401 without leaking which specific check failed."""


@dataclass
class OAuthIdentityInfo:
    provider: str
    subject: str
    email: str
    email_verified: bool
    name: str | None


def _fetch_jwks(provider: str) -> dict:
    cached = _jwks_cache.get(provider)
    if cached and time.time() - cached[0] < _JWKS_TTL_SECONDS:
        return cached[1]
    resp = httpx.get(_PROVIDERS[provider]["jwks_uri"], timeout=10.0)
    resp.raise_for_status()
    jwks = resp.json()
    _jwks_cache[provider] = (time.time(), jwks)
    return jwks


def _find_key(provider: str, kid: str | None) -> dict | None:
    jwks = _fetch_jwks(provider)
    key = next((k for k in jwks.get("keys", []) if k.get("kid") == kid), None)
    if key is not None:
        return key
    # Keys rotate; refresh once and retry before giving up.
    _jwks_cache.pop(provider, None)
    jwks = _fetch_jwks(provider)
    return next((k for k in jwks.get("keys", []) if k.get("kid") == kid), None)


def verify_id_token(provider: str, id_token: str) -> OAuthIdentityInfo:
    if provider not in _PROVIDERS:
        raise OAuthVerificationError(f"Unsupported identity provider '{provider}'")

    conf = _PROVIDERS[provider]
    client_id = getattr(get_settings(), conf["client_id_setting"])
    if not client_id:
        raise OAuthVerificationError(f"{provider} sign-in is not configured on this server")

    try:
        header = jwt.get_unverified_header(id_token)
    except JWTError as exc:
        raise OAuthVerificationError("Malformed token") from exc

    key = _find_key(provider, header.get("kid"))
    if key is None:
        raise OAuthVerificationError("Unable to find a matching signing key")

    try:
        claims = jwt.decode(
            id_token,
            key,
            algorithms=["RS256"],
            audience=client_id,
            options={"verify_at_hash": False},
        )
    except JWTError as exc:
        raise OAuthVerificationError("Token signature/audience verification failed") from exc

    issuer = claims.get("iss", "")
    if "issuers" in conf and issuer not in conf["issuers"]:
        raise OAuthVerificationError("Unexpected token issuer")
    if "issuer_prefix" in conf and not issuer.startswith(conf["issuer_prefix"]):
        raise OAuthVerificationError("Unexpected token issuer")

    email = claims.get("email")
    subject = claims.get("sub")
    if not email or not subject:
        raise OAuthVerificationError("Token did not include the expected identity claims")

    return OAuthIdentityInfo(
        provider=provider,
        subject=subject,
        email=email,
        email_verified=bool(claims.get("email_verified", True)),
        name=claims.get("name"),
    )
