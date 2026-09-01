import csv
import io
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_scheduler
from app.database import get_db
from app.models.enums import ScheduleRunStatus
from app.models.physician import Physician
from app.models.schedule import Assignment, ScheduleRun, SchedulingRule
from app.models.shift import ShiftInstance, ShiftType
from app.models.tenancy import User
from app.schemas.schedule import (
    AssignmentRead,
    FairnessRow,
    ScheduleGenerateRequest,
    ScheduleRunDetail,
    ScheduleRunRead,
    SchedulingRuleRead,
    SchedulingRuleUpdate,
)
from app.services.ai.explainer import summarize_schedule_run
from app.services.audit import log_audit
from app.services.notifications.notify import notify_schedule_published
from app.services.scheduling.fairness import build_fairness_report
from app.services.scheduling.service import get_or_create_rules, generate_schedule

router = APIRouter(tags=["schedules"])


# ---- scheduling rules ----


@router.get("/scheduling-rules", response_model=SchedulingRuleRead)
def get_rules(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> SchedulingRuleRead:
    rules = get_or_create_rules(db, current_user.org_id)
    return SchedulingRuleRead.model_validate(rules)


@router.patch("/scheduling-rules", response_model=SchedulingRuleRead)
def update_rules(
    payload: SchedulingRuleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_scheduler),
) -> SchedulingRuleRead:
    rules = get_or_create_rules(db, current_user.org_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(rules, field, value)
    db.commit()
    db.refresh(rules)
    return SchedulingRuleRead.model_validate(rules)


# ---- schedule generation ----


@router.post("/schedule-runs/generate", response_model=ScheduleRunDetail, status_code=201)
def generate(
    payload: ScheduleGenerateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_scheduler),
) -> ScheduleRunDetail:
    run = generate_schedule(
        db=db,
        org_id=current_user.org_id,
        site_id=payload.site_id,
        period_start=payload.period_start,
        period_end=payload.period_end,
        created_by_user_id=current_user.id,
        time_limit_seconds=payload.time_limit_seconds,
    )
    if payload.generate_ai_summary:
        fairness = build_fairness_report(db, run)
        run.ai_summary = summarize_schedule_run(run, fairness)
        db.commit()
        db.refresh(run)
    log_audit(
        db, current_user.org_id, "schedule_run.generate", "schedule_run", run.id, user_id=current_user.id,
        details={"period_start": str(run.period_start), "period_end": str(run.period_end), "unfilled": run.unfilled_shift_count},
    )
    db.commit()
    return _to_detail(db, run)


@router.get("/schedule-runs", response_model=list[ScheduleRunRead])
def list_runs(
    site_id: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ScheduleRunRead]:
    q = db.query(ScheduleRun).filter(ScheduleRun.org_id == current_user.org_id)
    if site_id:
        q = q.filter(ScheduleRun.site_id == site_id)
    return q.order_by(ScheduleRun.created_at.desc()).all()


@router.get("/schedule-runs/{run_id}", response_model=ScheduleRunDetail)
def get_run(run_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> ScheduleRunDetail:
    run = _get_run_or_404(db, current_user.org_id, run_id)
    return _to_detail(db, run)


@router.post("/schedule-runs/{run_id}/publish", response_model=ScheduleRunRead)
def publish_run(
    run_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_scheduler)
) -> ScheduleRunRead:
    run = _get_run_or_404(db, current_user.org_id, run_id)
    run.status = ScheduleRunStatus.PUBLISHED
    log_audit(db, current_user.org_id, "schedule_run.publish", "schedule_run", run.id, user_id=current_user.id)
    db.commit()
    db.refresh(run)

    _notify_physicians_of_publish(db, run)
    return ScheduleRunRead.model_validate(run)


@router.get("/schedule-runs/{run_id}/fairness", response_model=list[FairnessRow])
def get_fairness(
    run_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> list[FairnessRow]:
    run = _get_run_or_404(db, current_user.org_id, run_id)
    return build_fairness_report(db, run)


def _get_run_or_404(db: Session, org_id: str, run_id: str) -> ScheduleRun:
    run = db.query(ScheduleRun).filter(ScheduleRun.id == run_id, ScheduleRun.org_id == org_id).first()
    if run is None:
        raise HTTPException(status_code=404, detail="Schedule run not found")
    return run


def _to_detail(db: Session, run: ScheduleRun) -> ScheduleRunDetail:
    assignments = db.query(Assignment).filter(Assignment.schedule_run_id == run.id).all()
    data = ScheduleRunRead.model_validate(run).model_dump()
    data["assignments"] = [AssignmentRead.model_validate(a) for a in assignments]
    return ScheduleRunDetail(**data)


def _notify_physicians_of_publish(db: Session, run: ScheduleRun) -> None:
    assignments = db.query(Assignment).filter(Assignment.schedule_run_id == run.id).all()
    shift_count_by_physician: dict[str, int] = defaultdict(int)
    for a in assignments:
        shift_count_by_physician[a.physician_id] += 1
    if not shift_count_by_physician:
        return

    physicians = {
        p.id: p
        for p in db.query(Physician).filter(Physician.id.in_(shift_count_by_physician.keys())).all()
    }
    physician_users = {
        u.physician_id: u
        for u in db.query(User).filter(User.physician_id.in_(shift_count_by_physician.keys())).all()
    }
    for physician_id, count in shift_count_by_physician.items():
        user = physician_users.get(physician_id)
        physician = physicians.get(physician_id)
        if not user or not physician:
            continue
        notify_schedule_published(
            user.email, f"{physician.first_name} {physician.last_name}", run.period_start, run.period_end, count
        )


@router.get("/schedule-runs/{run_id}/export.csv")
def export_run_csv(
    run_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> Response:
    """The schedule as a CSV grid -- one row per shift, with who's on it.
    What gets pasted into a group email, posted in the department, or handed
    to a hospital's own system."""
    run = _get_run_or_404(db, current_user.org_id, run_id)

    rows = (
        db.query(ShiftInstance, ShiftType, Assignment, Physician)
        .join(ShiftType, ShiftInstance.shift_type_id == ShiftType.id)
        .outerjoin(Assignment, Assignment.shift_instance_id == ShiftInstance.id)
        .outerjoin(Physician, Assignment.physician_id == Physician.id)
        .filter(ShiftInstance.schedule_run_id == run.id)
        .order_by(ShiftInstance.date, ShiftInstance.start_datetime)
        .all()
    )

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["Date", "Day", "Shift", "Start", "End", "Category", "Physician", "Status"])
    for shift, shift_type, assignment, physician in rows:
        writer.writerow(
            [
                shift.date.isoformat(),
                shift.date.strftime("%a"),
                shift_type.name,
                shift.start_datetime.strftime("%H:%M"),
                shift.end_datetime.strftime("%H:%M"),
                shift.category.value + (" (holiday)" if shift.is_holiday else ""),
                f"{physician.first_name} {physician.last_name}" if physician else "UNFILLED",
                assignment.status.value if assignment else "open",
            ]
        )

    filename = f"schedule-{run.period_start}-to-{run.period_end}.csv"
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
