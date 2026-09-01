from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database import get_db
from app.models.enums import ScheduleRunStatus
from app.models.schedule import Assignment, ScheduleRun
from app.models.shift import ShiftInstance, ShiftType
from app.models.tenancy import Site, User
from app.schemas.schedule import AssignmentDetail

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
