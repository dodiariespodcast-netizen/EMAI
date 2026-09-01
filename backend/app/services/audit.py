"""Append-only audit trail. Call `log_audit` from any endpoint that
mutates something an administrator, malpractice carrier, or hospital
credentialing committee might later ask "who did this and when" about."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.tenancy import AuditLog


def log_audit(
    db: Session,
    org_id: str,
    action: str,
    entity_type: str,
    entity_id: str | None = None,
    user_id: str | None = None,
    details: dict | None = None,
) -> None:
    db.add(
        AuditLog(
            org_id=org_id,
            user_id=user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            details=details or {},
        )
    )
