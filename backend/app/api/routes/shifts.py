from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_scheduler
from app.database import get_db
from app.models.physician import Physician
from app.models.schedule import Assignment, ScheduleRun
from app.models.shift import ShiftInstance, ShiftType
from app.models.tenancy import Site, User
from app.schemas.shift import (
    EligiblePhysician,
    ShiftInstanceCreate,
    ShiftInstanceGenerate,
    ShiftInstanceRead,
    ShiftTypeCreate,
    ShiftTypeRead,
    SiteCreate,
    SiteRead,
)
from app.services.scheduling.service import get_or_create_rules
from app.services.scheduling.swap_conflicts import find_assignment_conflict

router = APIRouter(tags=["shifts"])


# ---- sites ----


@router.post("/sites", response_model=SiteRead, status_code=201)
def create_site(
    payload: SiteCreate, db: Session = Depends(get_db), current_user: User = Depends(require_scheduler)
) -> SiteRead:
    site = Site(org_id=current_user.org_id, **payload.model_dump())
    db.add(site)
    db.commit()
    db.refresh(site)
    return SiteRead.model_validate(site)


@router.get("/sites", response_model=list[SiteRead])
def list_sites(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> list[SiteRead]:
    return db.query(Site).filter(Site.org_id == current_user.org_id).all()


# ---- shift types ----


@router.post("/shift-types", response_model=ShiftTypeRead, status_code=201)
def create_shift_type(
    payload: ShiftTypeCreate, db: Session = Depends(get_db), current_user: User = Depends(require_scheduler)
) -> ShiftTypeRead:
    site = db.query(Site).filter(Site.id == payload.site_id, Site.org_id == current_user.org_id).first()
    if site is None:
        raise HTTPException(status_code=404, detail="Site not found")
    shift_type = ShiftType(org_id=current_user.org_id, **payload.model_dump())
    db.add(shift_type)
    db.commit()
    db.refresh(shift_type)
    return ShiftTypeRead.model_validate(shift_type)


@router.get("/shift-types", response_model=list[ShiftTypeRead])
def list_shift_types(
    site_id: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ShiftTypeRead]:
    q = db.query(ShiftType).filter(ShiftType.org_id == current_user.org_id)
    if site_id:
        q = q.filter(ShiftType.site_id == site_id)
    return q.all()


# ---- shift instances ----


@router.post("/shift-instances", response_model=ShiftInstanceRead, status_code=201)
def create_shift_instance(
    payload: ShiftInstanceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_scheduler),
) -> ShiftInstanceRead:
    shift_type = (
        db.query(ShiftType)
        .filter(ShiftType.id == payload.shift_type_id, ShiftType.org_id == current_user.org_id)
        .first()
    )
    if shift_type is None:
        raise HTTPException(status_code=404, detail="Shift type not found")

    instance = _build_instance(current_user.org_id, shift_type, payload.date, payload.is_holiday, payload.required_physicians)
    db.add(instance)
    db.commit()
    db.refresh(instance)
    return ShiftInstanceRead.model_validate(instance)


@router.post("/shift-instances/generate", response_model=list[ShiftInstanceRead], status_code=201)
def generate_shift_instances(
    payload: ShiftInstanceGenerate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_scheduler),
) -> list[ShiftInstanceRead]:
    """Creates one shift instance per day for a shift type across a date
    range -- the normal path for standing up a month's worth of coverage
    needs before running the optimizer."""
    shift_type = (
        db.query(ShiftType)
        .filter(ShiftType.id == payload.shift_type_id, ShiftType.org_id == current_user.org_id)
        .first()
    )
    if shift_type is None:
        raise HTTPException(status_code=404, detail="Shift type not found")
    if payload.end_date < payload.start_date:
        raise HTTPException(status_code=400, detail="end_date must be on or after start_date")

    holiday_set = set(payload.holiday_dates)
    instances = []
    d = payload.start_date
    while d <= payload.end_date:
        instances.append(_build_instance(current_user.org_id, shift_type, d, d in holiday_set, None))
        d += timedelta(days=1)

    db.add_all(instances)
    db.commit()
    for i in instances:
        db.refresh(i)
    return [ShiftInstanceRead.model_validate(i) for i in instances]


@router.get("/shift-instances", response_model=list[ShiftInstanceRead])
def list_shift_instances(
    site_id: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ShiftInstanceRead]:
    q = db.query(ShiftInstance).filter(ShiftInstance.org_id == current_user.org_id)
    if site_id:
        q = q.filter(ShiftInstance.site_id == site_id)
    if start_date:
        q = q.filter(ShiftInstance.date >= start_date)
    if end_date:
        q = q.filter(ShiftInstance.date <= end_date)
    return q.order_by(ShiftInstance.date).all()


def _build_instance(org_id, shift_type: ShiftType, day, is_holiday: bool, required_override: int | None) -> ShiftInstance:
    start_dt = datetime.combine(day, shift_type.start_time)
    end_dt = datetime.combine(day, shift_type.end_time)
    if end_dt <= start_dt:  # overnight shift wraps to the next calendar day
        end_dt += timedelta(days=1)
    return ShiftInstance(
        org_id=org_id,
        site_id=shift_type.site_id,
        shift_type_id=shift_type.id,
        date=day,
        start_datetime=start_dt,
        end_datetime=end_dt,
        category=shift_type.category,
        required_physicians=required_override or shift_type.required_physicians,
        is_holiday=is_holiday,
    )


@router.get("/shift-instances/{shift_instance_id}/eligible-physicians", response_model=list[EligiblePhysician])
def list_eligible_physicians(
    shift_instance_id: str,
    exclude_assignment_id: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_scheduler),
) -> list[EligiblePhysician]:
    """Who could cover this shift, and for anyone who couldn't, why. Backs the
    'assign someone' picker when a scheduler hand-edits the schedule."""
    shift = (
        db.query(ShiftInstance)
        .filter(ShiftInstance.id == shift_instance_id, ShiftInstance.org_id == current_user.org_id)
        .first()
    )
    if shift is None:
        raise HTTPException(status_code=404, detail="Shift not found")

    rules = get_or_create_rules(db, current_user.org_id)
    physicians = (
        db.query(Physician)
        .filter(Physician.org_id == current_user.org_id, Physician.is_active.is_(True))
        .order_by(Physician.last_name, Physician.first_name)
        .all()
    )

    run = db.query(ScheduleRun).filter(ScheduleRun.id == shift.schedule_run_id).first() if shift.schedule_run_id else None
    load: dict[str, int] = {}
    if run is not None:
        rows = (
            db.query(Assignment.physician_id, func.count(Assignment.id))
            .filter(Assignment.schedule_run_id == run.id)
            .group_by(Assignment.physician_id)
            .all()
        )
        load = {pid: count for pid, count in rows}

    results = []
    for physician in physicians:
        conflict = find_assignment_conflict(
            db, current_user.org_id, shift, physician.id, rules, exclude_assignment_id=exclude_assignment_id
        )
        results.append(
            EligiblePhysician(
                physician_id=physician.id,
                name=f"{physician.first_name} {physician.last_name}",
                employment_type=physician.employment_type.value,
                conflict=conflict,
                assigned_shifts_in_period=load.get(physician.id, 0),
            )
        )
    # Conflict-free first, then least-loaded -- the order a scheduler filling a
    # hole actually wants to read.
    results.sort(key=lambda r: (r.conflict is not None, r.assigned_shifts_in_period, r.name))
    return results
