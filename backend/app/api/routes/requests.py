from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_scheduler
from app.database import get_db
from app.models.enums import RequestStatus
from app.models.physician import Physician
from app.models.requests import ShiftPreference, TimeOffRequest
from app.models.tenancy import User
from app.schemas.requests import (
    ShiftPreferenceCreate,
    ShiftPreferenceRead,
    TimeOffRequestCreate,
    TimeOffRequestFromText,
    TimeOffRequestRead,
    TimeOffRequestUpdate,
)
from app.services.ai.request_parser import parse_time_off_text
from app.services.audit import log_audit
from app.services.notifications.notify import notify_time_off_status_changed

router = APIRouter(tags=["requests"])


def _check_physician(db: Session, org_id: str, physician_id: str) -> None:
    if not db.query(Physician).filter(Physician.id == physician_id, Physician.org_id == org_id).first():
        raise HTTPException(status_code=404, detail="Physician not found")


# ---- time off ----


@router.post("/time-off-requests", response_model=TimeOffRequestRead, status_code=201)
def create_time_off_request(
    payload: TimeOffRequestCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TimeOffRequestRead:
    _check_physician(db, current_user.org_id, payload.physician_id)
    if payload.end_date < payload.start_date:
        raise HTTPException(status_code=400, detail="end_date must be on or after start_date")
    req = TimeOffRequest(org_id=current_user.org_id, **payload.model_dump())
    db.add(req)
    db.commit()
    db.refresh(req)
    return TimeOffRequestRead.model_validate(req)


@router.post("/time-off-requests/from-text", response_model=TimeOffRequestRead, status_code=201)
def create_time_off_request_from_text(
    payload: TimeOffRequestFromText,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TimeOffRequestRead:
    """AI intake path: a physician types a plain-English ask and we parse it
    into a structured request (Claude when configured, deterministic
    fallback otherwise) instead of making them fill out a form."""
    _check_physician(db, current_user.org_id, payload.physician_id)
    parsed = parse_time_off_text(payload.text)
    req = TimeOffRequest(
        org_id=current_user.org_id,
        physician_id=payload.physician_id,
        start_date=parsed.start_date,
        end_date=parsed.end_date,
        request_type=parsed.request_type,
        priority=parsed.priority,
        reason=parsed.reason,
        raw_text=payload.text,
    )
    db.add(req)
    db.commit()
    db.refresh(req)
    return TimeOffRequestRead.model_validate(req)


@router.get("/time-off-requests", response_model=list[TimeOffRequestRead])
def list_time_off_requests(
    physician_id: str | None = None,
    status_filter: RequestStatus | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[TimeOffRequestRead]:
    q = db.query(TimeOffRequest).filter(TimeOffRequest.org_id == current_user.org_id)
    if physician_id:
        q = q.filter(TimeOffRequest.physician_id == physician_id)
    if status_filter:
        q = q.filter(TimeOffRequest.status == status_filter)
    return q.order_by(TimeOffRequest.start_date).all()


@router.patch("/time-off-requests/{request_id}", response_model=TimeOffRequestRead)
def update_time_off_request_status(
    request_id: str,
    payload: TimeOffRequestUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_scheduler),
) -> TimeOffRequestRead:
    req = (
        db.query(TimeOffRequest)
        .filter(TimeOffRequest.id == request_id, TimeOffRequest.org_id == current_user.org_id)
        .first()
    )
    if req is None:
        raise HTTPException(status_code=404, detail="Request not found")
    req.status = payload.status
    log_audit(
        db, current_user.org_id, "time_off_request.status_change", "time_off_request", req.id,
        user_id=current_user.id, details={"status": payload.status.value},
    )
    db.commit()
    db.refresh(req)

    physician_user = db.query(User).filter(User.physician_id == req.physician_id).first()
    if physician_user:
        physician = db.query(Physician).filter(Physician.id == req.physician_id).first()
        notify_time_off_status_changed(
            physician_user.email, f"{physician.first_name} {physician.last_name}", req.start_date, req.end_date, payload.status.value
        )
    return TimeOffRequestRead.model_validate(req)


# ---- shift preferences ----


@router.post("/shift-preferences", response_model=ShiftPreferenceRead, status_code=201)
def create_shift_preference(
    payload: ShiftPreferenceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ShiftPreferenceRead:
    _check_physician(db, current_user.org_id, payload.physician_id)
    pref = ShiftPreference(org_id=current_user.org_id, **payload.model_dump())
    db.add(pref)
    db.commit()
    db.refresh(pref)
    return ShiftPreferenceRead.model_validate(pref)


@router.get("/shift-preferences", response_model=list[ShiftPreferenceRead])
def list_shift_preferences(
    physician_id: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ShiftPreferenceRead]:
    q = db.query(ShiftPreference).filter(ShiftPreference.org_id == current_user.org_id)
    if physician_id:
        q = q.filter(ShiftPreference.physician_id == physician_id)
    return q.all()
