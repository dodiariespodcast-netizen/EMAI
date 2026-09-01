from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import require_scheduler
from app.database import get_db
from app.models.tenancy import AuditLog, User
from app.schemas.audit import AuditLogRead

router = APIRouter(prefix="/audit-log", tags=["audit"])


@router.get("", response_model=list[AuditLogRead])
def list_audit_log(
    entity_type: str | None = None,
    entity_id: str | None = None,
    limit: int = 200,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_scheduler),
) -> list[AuditLogRead]:
    q = db.query(AuditLog).filter(AuditLog.org_id == current_user.org_id)
    if entity_type:
        q = q.filter(AuditLog.entity_type == entity_type)
    if entity_id:
        q = q.filter(AuditLog.entity_id == entity_id)
    return q.order_by(AuditLog.created_at.desc()).limit(min(limit, 1000)).all()
