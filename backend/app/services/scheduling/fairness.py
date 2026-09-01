"""Builds the fairness report shown to admins and physicians: how each
person's actual workload compares to their fair-share target, and how many
of their preferred time-off requests were honored."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.enums import RequestPriority, RequestStatus
from app.models.physician import Physician
from app.models.requests import TimeOffRequest
from app.models.schedule import Assignment, ScheduleRun
from app.schemas.schedule import FairnessRow


def build_fairness_report(db: Session, run: ScheduleRun) -> list[FairnessRow]:
    physicians = {p.id: p for p in db.query(Physician).filter(Physician.org_id == run.org_id).all()}
    per_physician_stats = {row["physician_id"]: row for row in run.stats.get("per_physician", [])}

    preferred_requests = (
        db.query(TimeOffRequest)
        .filter(
            TimeOffRequest.org_id == run.org_id,
            TimeOffRequest.priority == RequestPriority.PREFERRED,
            TimeOffRequest.start_date <= run.period_end,
            TimeOffRequest.end_date >= run.period_start,
        )
        .all()
    )
    assigned_shift_ids_by_physician: dict[str, set[str]] = {}
    for a in db.query(Assignment).filter(Assignment.schedule_run_id == run.id).all():
        assigned_shift_ids_by_physician.setdefault(a.physician_id, set()).add(a.shift_instance_id)

    from app.models.shift import ShiftInstance

    shift_dates = {
        s.id: s.date
        for s in db.query(ShiftInstance).filter(ShiftInstance.schedule_run_id == run.id).all()
    }

    granted: dict[str, int] = {}
    total: dict[str, int] = {}
    for r in preferred_requests:
        total[r.physician_id] = total.get(r.physician_id, 0) + 1
        assigned_dates = {
            shift_dates[sid] for sid in assigned_shift_ids_by_physician.get(r.physician_id, set())
        }
        conflict = any(r.start_date <= d <= r.end_date for d in assigned_dates)
        if not conflict:
            granted[r.physician_id] = granted.get(r.physician_id, 0) + 1

    rows: list[FairnessRow] = []
    for pid, physician in physicians.items():
        stats = per_physician_stats.get(pid, {})
        rows.append(
            FairnessRow(
                physician_id=pid,
                physician_name=f"{physician.first_name} {physician.last_name}",
                total_shifts=stats.get("total_shifts", 0),
                target_shifts=stats.get("target_shifts", 0.0),
                night_shifts=stats.get("night_shifts", 0),
                weekend_shifts=stats.get("weekend_shifts", 0),
                holiday_shifts=stats.get("holiday_shifts", 0),
                preferred_requests_granted=granted.get(pid, 0),
                preferred_requests_total=total.get(pid, 0),
            )
        )
    rows.sort(key=lambda r: r.physician_name)
    return rows
