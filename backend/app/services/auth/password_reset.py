"""Password reset / invite tokens.

One mechanism backs two flows that are the same underneath:
  * "I forgot my password"  -- the user asks for a link
  * "an admin added me"     -- the admin creates the account and the user
                               sets their own password from the link

Only a SHA-256 hash of each token is persisted, so leaked database rows
can't be replayed as working reset links.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.tenancy import PasswordResetToken, User

INVITE_TTL_HOURS = 72
RESET_TTL_HOURS = 2


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _aware(value: datetime) -> datetime:
    """SQLite hands back naive datetimes even for timezone=True columns;
    normalize so comparisons against an aware "now" don't explode."""
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def issue_token(db: Session, user: User, purpose: str = "reset") -> str:
    """Creates a token for `user`, invalidating any outstanding ones for the
    same purpose, and returns the *plaintext* token (the only time it exists)."""
    now = datetime.now(timezone.utc)
    outstanding = (
        db.query(PasswordResetToken)
        .filter(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.purpose == purpose,
            PasswordResetToken.used_at.is_(None),
        )
        .all()
    )
    for row in outstanding:
        row.used_at = now

    token = secrets.token_urlsafe(32)
    ttl = INVITE_TTL_HOURS if purpose == "invite" else RESET_TTL_HOURS
    db.add(
        PasswordResetToken(
            user_id=user.id,
            token_hash=_hash(token),
            purpose=purpose,
            expires_at=now + timedelta(hours=ttl),
        )
    )
    return token


def consume_token(db: Session, token: str) -> User | None:
    """Validates and burns a token, returning the user it belongs to (or None
    if it's unknown, already used, or expired)."""
    row = db.query(PasswordResetToken).filter(PasswordResetToken.token_hash == _hash(token)).first()
    if row is None or row.used_at is not None:
        return None
    if _aware(row.expires_at) < datetime.now(timezone.utc):
        return None

    row.used_at = datetime.now(timezone.utc)
    return db.query(User).filter(User.id == row.user_id).first()


def build_link(token: str, purpose: str = "reset") -> str:
    """The URL we email. Points at the frontend, which then POSTs the token
    back to /auth/password-reset/confirm."""
    base = get_settings().frontend_base_url.rstrip("/")
    path = "set-password" if purpose == "invite" else "reset-password"
    return f"{base}/{path}?token={token}"
