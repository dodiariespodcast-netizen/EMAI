from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_scheduler
from app.database import get_db
from app.models.enums import ScheduleRunStatus
from app.models.schedule import Assignment, ScheduleRun
from app.models.shift import ShiftInstance, ShiftType
from app.models.tenancy import Site, User
from app.schemas.schedule import AssignmentCreate, AssignmentDetail, AssignmentReassign
from app.services.audit import log_audit
from app.services.scheduling.service import get_or_create_rules
from app.services.scheduling.swap_conflicts import find_assignment_conflict

router = APIRouter(prefix="/assignments", tags=["assignments"])


def _query(db: Session, org_id: str):
    return (
        db.query(Assignment, ShiftInstance, ShiftType, Site, ScheduleRun)
        .join(ShiftInstance, Assignment.shift_instance_id == ShiftInstance.id)
        .join(ShiftType, ShiftInstance.shift_type_id == ShiftType.id)
        .join(Site, ShiftInstance.site_id == Site.id)
        .join(ScheduleRun, Assignment.schedule_run_id == ScheduleRun.id)
        .filter(Assignment.org_id == org_id)
    )


def _to_detail(assignment: Assignment, shift: ShiftInstance, shift_type: ShiftType, site: Site, run: ScheduleRun) -> AssignmentDetail:
    return AssignmentDetail(
        id=assignment.id,
        shift_instance_id=assignment.shift_instance_id,
        physician_id=assignment.physician_id,
        status=assignment.status.value,
        schedule_run_id=run.id,
        schedule_run_status=run.status,
        site_id=site.id,
        site_name=site.name,
        date=shift.date,
        start_datetime=shift.start_datetime,
        end_datetime=shift.end_datetime,
        category=shift.category.value,
        shift_type_name=shift_type.name,
    )


@router.get("", response_model=list[AssignmentDetail])
def list_assignments(
    physician_id: str | None = None,
    site_id: str | None = None,
    published_only: bool = True,
    start_date: str | None = None,
    end_date: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[AssignmentDetail]:
    """Denormalized assignment listing -- the query a 'my schedule' view or
    the shift-swap marketplace needs, without making the client separately
    join shift instances and schedule runs itself."""
    q = _query(db, current_user.org_id)
    if physician_id:
        q = q.filter(Assignment.physician_id == physician_id)
    if site_id:
        q = q.filter(ShiftInstance.site_id == site_id)
    if published_only:
        q = q.filter(ScheduleRun.status == ScheduleRunStatus.PUBLISHED)
    if start_date:
        q = q.filter(ShiftInstance.date >= start_date)
    if end_date:
        q = q.filter(ShiftInstance.date <= end_date)
    rows = q.order_by(ShiftInstance.date).all()
    return [_to_detail(*row) for row in rows]


@router.get("/{assignment_id}", response_model=AssignmentDetail)
def get_assignment(
    assignment_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> AssignmentDetail:
    row = _query(db, current_user.org_id).filter(Assignment.id == assignment_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Assignment not found")
    return _to_detail(*row)


@router.post("", response_model=AssignmentDetail, status_code=201)
def create_assignment(
    payload: AssignmentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_scheduler),
) -> AssignmentDetail:
    """Hand-place a physician on a shift. Every real scheduler needs to
    override the optimizer sometimes -- a late call-out, a deal struck in the
    hallway -- so this exists, but it runs the same hard-rule check the solver
    does and refuses (409) unless `force` is set, in which case the override
    and its reason are written to the audit log."""
    shift = (
        db.query(ShiftInstance)
        .filter(ShiftInstance.id == payload.shift_instance_id, ShiftInstance.org_id == current_user.org_id)
        .first()
    )
    if shift is None:
        raise HTTPException(status_code=404, detail="Shift not found")
    if shift.schedule_run_id is None:
        raise HTTPException(
            status_code=400,
            detail="This shift isn't part of a schedule run yet -- generate a schedule for its period first",
        )

    rules = get_or_create_rules(db, current_user.org_id)
    conflict = find_assignment_conflict(db, current_user.org_id, shift, payload.physician_id, rules)
    if conflict and not payload.force:
        raise HTTPException(status_code=409, detail=conflict)

    assignment = Assignment(
        org_id=current_user.org_id,
        schedule_run_id=shift.schedule_run_id,
        shift_instance_id=shift.id,
        physician_id=payload.physician_id,
    )
    db.add(assignment)
    db.flush()
    log_audit(
        db, current_user.org_id, "assignment.create", "assignment", assignment.id, user_id=current_user.id,
        details={
            "shift_instance_id": shift.id,
            "physician_id": payload.physician_id,
            "forced_over_conflict": conflict if payload.force and conflict else None,
            "override_reason": payload.override_reason,
        },
    )
    db.commit()

    row = _query(db, current_user.org_id).filter(Assignment.id == assignment.id).first()
    return _to_detail(*row)


@router.patch("/{assignment_id}", response_model=AssignmentDetail)
def reassign_assignment(
    assignment_id: str,
    payload: AssignmentReassign,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_scheduler),
) -> AssignmentDetail:
    """Move an existing shift to a different physician."""
    assignment = (
        db.query(Assignment)
        .filter(Assignment.id == assignment_id, Assignment.org_id == current_user.org_id)
        .first()
    )
    if assignment is None:
        raise HTTPException(status_code=404, detail="Assignment not found")
    shift = db.query(ShiftInstance).filter(ShiftInstance.id == assignment.shift_instance_id).first()

    rules = get_or_create_rules(db, current_user.org_id)
    conflict = find_assignment_conflict(
        db, current_user.org_id, shift, payload.physician_id, rules, exclude_assignment_id=assignment.id
    )
    if conflict and not payload.force:
        raise HTTPException(status_code=409, detail=conflict)

    previous_physician_id = assignment.physician_id
    assignment.physician_id = payload.physician_id
    log_audit(
        db, current_user.org_id, "assignment.reassign", "assignment", assignment.id, user_id=current_user.id,
        details={
            "from_physician_id": previous_physician_id,
            "to_physician_id": payload.physician_id,
            "forced_over_conflict": conflict if payload.force and conflict else None,
            "override_reason": payload.override_reason,
        },
    )
    db.commit()

    row = _query(db, current_user.org_id).filter(Assignment.id == assignment.id).first()
    return _to_detail(*row)


@router.delete("/{assignment_id}", status_code=204)
def delete_assignment(
    assignment_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_scheduler),
) -> None:
    """Unassign a shift, leaving it open. Shows up as unfilled on the
    schedule and is claimable from the swap marketplace."""
    assignment = (
        db.query(Assignment)
        .filter(Assignment.id == assignment_id, Assignment.org_id == current_user.org_id)
        .first()
    )
    if assignment is None:
        raise HTTPException(status_code=404, detail="Assignment not found")

    log_audit(
        db, current_user.org_id, "assignment.delete", "assignment", assignment.id, user_id=current_user.id,
        details={"physician_id": assignment.physician_id, "shift_instance_id": assignment.shift_instance_id},
    )
    db.delete(assignment)
    db.commit()
