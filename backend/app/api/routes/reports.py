"""Reporting and exports -- the numbers a group runs on between schedules.

Hours and cost come straight from published assignments joined to shift
durations, so payroll/invoicing reconciles against exactly what was
scheduled. For a locums agency this is the billing basis; for an EM group
it's the productivity/pay-period report.
"""

from __future__ import annotations

import csv
import io
from datetime import date

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_scheduler
from app.database import get_db
from app.models.enums import ScheduleRunStatus
from app.models.physician import Physician
from app.models.schedule import Assignment, ScheduleRun
from app.models.shift import ShiftInstance, ShiftType
from app.models.tenancy import Site, User
from app.schemas.report import CoverageReport, HoursReport, HoursRow

router = APIRouter(prefix="/reports", tags=["reports"])


def _worked_rows(db: Session, org_id: str, start: date, end: date, site_id: str | None, published_only: bool):
    q = (
        db.query(Assignment, ShiftInstance, ShiftType)
        .join(ShiftInstance, Assignment.shift_instance_id == ShiftInstance.id)
        .join(ShiftType, ShiftInstance.shift_type_id == ShiftType.id)
        .join(ScheduleRun, Assignment.schedule_run_id == ScheduleRun.id)
        .filter(
            Assignment.org_id == org_id,
            ShiftInstance.date >= start,
            ShiftInstance.date <= end,
        )
    )
    if site_id:
        q = q.filter(ShiftInstance.site_id == site_id)
    if published_only:
        q = q.filter(ScheduleRun.status == ScheduleRunStatus.PUBLISHED)
    return q.all()


@router.get("/hours", response_model=HoursReport)
def hours_report(
    start_date: date = Query(...),
    end_date: date = Query(...),
    site_id: str | None = None,
    published_only: bool = True,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_scheduler),
) -> HoursReport:
    """Hours worked and estimated cost per physician for a pay period.

    Cost is `hours x hourly_rate` and is only an estimate -- it reflects what
    was scheduled, not what was actually clocked or invoiced, and physicians
    without a rate on file contribute hours but no cost."""
    rows = _worked_rows(db, current_user.org_id, start_date, end_date, site_id, published_only)
    physicians = {p.id: p for p in db.query(Physician).filter(Physician.org_id == current_user.org_id).all()}

    tally: dict[str, dict] = {}
    for assignment, shift, shift_type in rows:
        bucket = tally.setdefault(
            assignment.physician_id,
            {"shifts": 0, "hours": 0.0, "night_hours": 0.0, "weekend_hours": 0.0, "holiday_hours": 0.0},
        )
        hours = shift_type.duration_hours
        bucket["shifts"] += 1
        bucket["hours"] += hours
        if shift.category.value == "night":
            bucket["night_hours"] += hours
        if shift.date.weekday() >= 5:
            bucket["weekend_hours"] += hours
        if shift.is_holiday:
            bucket["holiday_hours"] += hours

    report_rows: list[HoursRow] = []
    for physician_id, bucket in tally.items():
        physician = physicians.get(physician_id)
        if physician is None:
            continue
        rate = physician.hourly_rate
        report_rows.append(
            HoursRow(
                physician_id=physician_id,
                physician_name=f"{physician.first_name} {physician.last_name}",
                employment_type=physician.employment_type.value,
                shifts=bucket["shifts"],
                hours=round(bucket["hours"], 2),
                night_hours=round(bucket["night_hours"], 2),
                weekend_hours=round(bucket["weekend_hours"], 2),
                holiday_hours=round(bucket["holiday_hours"], 2),
                hourly_rate=rate,
                estimated_cost=round(bucket["hours"] * rate, 2) if rate is not None else None,
            )
        )
    report_rows.sort(key=lambda r: r.physician_name)

    return HoursReport(
        period_start=start_date,
        period_end=end_date,
        rows=report_rows,
        total_shifts=sum(r.shifts for r in report_rows),
        total_hours=round(sum(r.hours for r in report_rows), 2),
        total_estimated_cost=round(sum(r.estimated_cost or 0.0 for r in report_rows), 2),
        physicians_missing_rate=[r.physician_name for r in report_rows if r.hourly_rate is None],
    )


@router.get("/hours.csv")
def hours_report_csv(
    start_date: date = Query(...),
    end_date: date = Query(...),
    site_id: str | None = None,
    published_only: bool = True,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_scheduler),
) -> Response:
    """Same report as a CSV, for handing to payroll or a billing system."""
    report = hours_report(start_date, end_date, site_id, published_only, db, current_user)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "Physician",
            "Employment type",
            "Shifts",
            "Hours",
            "Night hours",
            "Weekend hours",
            "Holiday hours",
            "Hourly rate",
            "Estimated cost",
        ]
    )
    for row in report.rows:
        writer.writerow(
            [
                row.physician_name,
                row.employment_type,
                row.shifts,
                row.hours,
                row.night_hours,
                row.weekend_hours,
                row.holiday_hours,
                "" if row.hourly_rate is None else row.hourly_rate,
                "" if row.estimated_cost is None else row.estimated_cost,
            ]
        )
    writer.writerow([])
    writer.writerow(["TOTAL", "", report.total_shifts, report.total_hours, "", "", "", "", report.total_estimated_cost])

    filename = f"hours-{start_date}-to-{end_date}.csv"
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/coverage", response_model=CoverageReport)
def coverage_report(
    start_date: date = Query(...),
    end_date: date = Query(...),
    site_id: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CoverageReport:
    """How much of the required coverage is actually staffed, and which
    specific shifts are still short."""
    shift_q = db.query(ShiftInstance).filter(
        ShiftInstance.org_id == current_user.org_id,
        ShiftInstance.date >= start_date,
        ShiftInstance.date <= end_date,
    )
    if site_id:
        shift_q = shift_q.filter(ShiftInstance.site_id == site_id)
    shifts = shift_q.order_by(ShiftInstance.date).all()

    shift_ids = [s.id for s in shifts]
    filled: dict[str, int] = {}
    if shift_ids:
        for assignment in db.query(Assignment).filter(Assignment.shift_instance_id.in_(shift_ids)).all():
            filled[assignment.shift_instance_id] = filled.get(assignment.shift_instance_id, 0) + 1

    shift_types = {st.id: st for st in db.query(ShiftType).filter(ShiftType.org_id == current_user.org_id).all()}

    required = sum(s.required_physicians for s in shifts)
    staffed = sum(min(filled.get(s.id, 0), s.required_physicians) for s in shifts)
    gaps = []
    for s in shifts:
        short = s.required_physicians - filled.get(s.id, 0)
        if short > 0:
            gaps.append(
                {
                    "shift_instance_id": s.id,
                    "date": str(s.date),
                    "shift_type": shift_types[s.shift_type_id].name if s.shift_type_id in shift_types else s.category.value,
                    "category": s.category.value,
                    "short_by": short,
                }
            )

    return CoverageReport(
        period_start=start_date,
        period_end=end_date,
        required_slots=required,
        staffed_slots=staffed,
        coverage_rate=round(staffed / required, 4) if required else 1.0,
        gaps=gaps,
    )
