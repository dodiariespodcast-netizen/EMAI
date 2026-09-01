from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_scheduler
from app.database import get_db
from app.models.enums import UserRole
from app.models.physician import Physician, PhysicianSite
from app.models.tenancy import User
from app.schemas.physician import PhysicianCreate, PhysicianPreferencesUpdate, PhysicianRead, PhysicianUpdate

router = APIRouter(prefix="/physicians", tags=["physicians"])


def _to_read(physician: Physician, db: Session) -> PhysicianRead:
    site_ids = [
        ps.site_id for ps in db.query(PhysicianSite).filter(PhysicianSite.physician_id == physician.id)
    ]
    data = PhysicianRead.model_validate(physician).model_dump()
    data["site_ids"] = site_ids
    return PhysicianRead(**data)


@router.post("", response_model=PhysicianRead, status_code=201)
def create_physician(
    payload: PhysicianCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_scheduler),
) -> PhysicianRead:
    data = payload.model_dump(exclude={"site_ids"})
    physician = Physician(org_id=current_user.org_id, **data)
    db.add(physician)
    db.flush()
    for site_id in payload.site_ids:
        db.add(PhysicianSite(physician_id=physician.id, site_id=site_id))
    db.commit()
    db.refresh(physician)
    return _to_read(physician, db)


@router.get("", response_model=list[PhysicianRead])
def list_physicians(
    active_only: bool = True,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[PhysicianRead]:
    q = db.query(Physician).filter(Physician.org_id == current_user.org_id)
    if active_only:
        q = q.filter(Physician.is_active.is_(True))
    return [_to_read(p, db) for p in q.all()]


@router.get("/{physician_id}", response_model=PhysicianRead)
def get_physician(
    physician_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> PhysicianRead:
    physician = (
        db.query(Physician)
        .filter(Physician.id == physician_id, Physician.org_id == current_user.org_id)
        .first()
    )
    if physician is None:
        raise HTTPException(status_code=404, detail="Physician not found")
    return _to_read(physician, db)


@router.patch("/{physician_id}", response_model=PhysicianRead)
def update_physician(
    physician_id: str,
    payload: PhysicianUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_scheduler),
) -> PhysicianRead:
    physician = (
        db.query(Physician)
        .filter(Physician.id == physician_id, Physician.org_id == current_user.org_id)
        .first()
    )
    if physician is None:
        raise HTTPException(status_code=404, detail="Physician not found")

    updates = payload.model_dump(exclude_unset=True, exclude={"site_ids"})
    for field, value in updates.items():
        setattr(physician, field, value)

    if payload.site_ids is not None:
        db.query(PhysicianSite).filter(PhysicianSite.physician_id == physician.id).delete()
        for site_id in payload.site_ids:
            db.add(PhysicianSite(physician_id=physician.id, site_id=site_id))

    db.commit()
    db.refresh(physician)
    return _to_read(physician, db)


@router.patch("/{physician_id}/preferences", response_model=PhysicianRead)
def update_own_preferences(
    physician_id: str,
    payload: PhysicianPreferencesUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PhysicianRead:
    """Self-service preference editing: a physician can update their own
    night/weekend/holiday preference without scheduler privileges. A
    scheduler can also use this (or the full PATCH /physicians/{id})."""
    is_self = current_user.physician_id == physician_id
    is_scheduler = current_user.role in (UserRole.OWNER, UserRole.ADMIN, UserRole.SCHEDULER)
    if not is_self and not is_scheduler:
        raise HTTPException(status_code=403, detail="Not authorized to edit this physician's preferences")

    physician = (
        db.query(Physician)
        .filter(Physician.id == physician_id, Physician.org_id == current_user.org_id)
        .first()
    )
    if physician is None:
        raise HTTPException(status_code=404, detail="Physician not found")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(physician, field, value)
    db.commit()
    db.refresh(physician)
    return _to_read(physician, db)


@router.delete("/{physician_id}", status_code=204)
def deactivate_physician(
    physician_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_scheduler),
) -> None:
    """Soft delete: physicians are never hard-deleted so historical
    schedules keep valid references."""
    physician = (
        db.query(Physician)
        .filter(Physician.id == physician_id, Physician.org_id == current_user.org_id)
        .first()
    )
    if physician is None:
        raise HTTPException(status_code=404, detail="Physician not found")
    physician.is_active = False
    db.commit()
