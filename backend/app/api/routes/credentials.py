from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_scheduler
from app.database import get_db
from app.models.physician import Credential, Physician
from app.models.tenancy import User
from app.schemas.credential import CredentialCreate, CredentialRead, CredentialUpdate
from app.services.audit import log_audit

router = APIRouter(prefix="/credentials", tags=["credentials"])


@router.post("", response_model=CredentialRead, status_code=201)
def create_credential(
    payload: CredentialCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_scheduler),
) -> CredentialRead:
    if not db.query(Physician).filter(
        Physician.id == payload.physician_id, Physician.org_id == current_user.org_id
    ).first():
        raise HTTPException(status_code=404, detail="Physician not found")
    credential = Credential(org_id=current_user.org_id, **payload.model_dump())
    db.add(credential)
    db.flush()
    log_audit(db, current_user.org_id, "credential.create", "credential", credential.id, user_id=current_user.id)
    db.commit()
    db.refresh(credential)
    return CredentialRead.model_validate(credential)


@router.get("", response_model=list[CredentialRead])
def list_credentials(
    physician_id: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[CredentialRead]:
    q = db.query(Credential).filter(Credential.org_id == current_user.org_id)
    if physician_id:
        q = q.filter(Credential.physician_id == physician_id)
    return q.order_by(Credential.expires_on).all()


@router.get("/expiring", response_model=list[CredentialRead])
def list_expiring_credentials(
    within_days: int = 60,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[CredentialRead]:
    """The compliance dashboard query: everything expiring (or already
    expired) within the window, soonest first. This is the single query a
    locums agency's whole risk posture depends on."""
    cutoff = date.today() + timedelta(days=within_days)
    return (
        db.query(Credential)
        .filter(
            Credential.org_id == current_user.org_id,
            Credential.expires_on.is_not(None),
            Credential.expires_on <= cutoff,
        )
        .order_by(Credential.expires_on)
        .all()
    )


@router.patch("/{credential_id}", response_model=CredentialRead)
def update_credential(
    credential_id: str,
    payload: CredentialUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_scheduler),
) -> CredentialRead:
    credential = (
        db.query(Credential)
        .filter(Credential.id == credential_id, Credential.org_id == current_user.org_id)
        .first()
    )
    if credential is None:
        raise HTTPException(status_code=404, detail="Credential not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(credential, field, value)
    log_audit(db, current_user.org_id, "credential.update", "credential", credential.id, user_id=current_user.id)
    db.commit()
    db.refresh(credential)
    return CredentialRead.model_validate(credential)


@router.delete("/{credential_id}", status_code=204)
def delete_credential(
    credential_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_scheduler)
) -> None:
    credential = (
        db.query(Credential)
        .filter(Credential.id == credential_id, Credential.org_id == current_user.org_id)
        .first()
    )
    if credential is None:
        raise HTTPException(status_code=404, detail="Credential not found")
    db.delete(credential)
    log_audit(db, current_user.org_id, "credential.delete", "credential", credential_id, user_id=current_user.id)
    db.commit()
