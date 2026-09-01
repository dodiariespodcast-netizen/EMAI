"""Orchestrates a schedule generation request: load the relevant slice of
the database into the solver's domain model, run the optimizer, persist the
result as a ScheduleRun + Assignments, and (optionally) kick off an AI
summary of the outcome."""

from __future__ import annotations

from datetime import date, datetime, time, timezone

from sqlalchemy.orm import Session

from app.models.enums import RequestPriority, RequestStatus, ScheduleRunStatus
from app.models.physician import Physician, PhysicianSite
from app.models.requests import ShiftPreference, TimeOffRequest
from app.models.schedule import Assignment, ScheduleRun, SchedulingRule
from app.models.shift import ShiftInstance
from app.services.scheduling.domain import (
    PhysicianInput,
    PreferenceBlock,
    RuleConfig,
    ScheduleInput,
    ShiftInstanceInput,
    TimeOffBlock,
)
from app.services.scheduling.engine import solve_schedule


def get_or_create_rules(db: Session, org_id: str) -> SchedulingRule:
    rules = db.query(SchedulingRule).filter(SchedulingRule.org_id == org_id).first()
    if rules is None:
        rules = SchedulingRule(org_id=org_id)
        db.add(rules)
        db.commit()
        db.refresh(rules)
    return rules


def _build_schedule_input(
    db: Session,
    org_id: str,
    site_id: str,
    period_start: date,
    period_end: date,
    time_limit_seconds: float | None,
) -> tuple[ScheduleInput, list[ShiftInstance]]:
    rules_row = get_or_create_rules(db, org_id)

    physicians_rows = (
        db.query(Physician)
        .filter(Physician.org_id == org_id, Physician.is_active.is_(True))
        .all()
    )
    site_map: dict[str, set[str]] = {}
    for ps in db.query(PhysicianSite).filter(
        PhysicianSite.physician_id.in_([p.id for p in physicians_rows])
    ):
        site_map.setdefault(ps.physician_id, set()).add(ps.site_id)

    physicians = [
        PhysicianInput(
            id=p.id,
            name=f"{p.first_name} {p.last_name}",
            fte=p.fte,
            seniority_years=p.seniority_years,
            night_preference=p.night_preference,
            weekend_preference=p.weekend_preference,
            holiday_preference=p.holiday_preference,
            eligible_site_ids=frozenset(site_map.get(p.id, set())),
            max_consecutive_shifts=p.max_consecutive_shifts,
            min_rest_hours=p.min_rest_hours,
            max_shifts_per_period=p.max_shifts_per_period,
        )
        for p in physicians_rows
    ]

    shift_rows = (
        db.query(ShiftInstance)
        .filter(
            ShiftInstance.org_id == org_id,
            ShiftInstance.site_id == site_id,
            ShiftInstance.date >= period_start,
            ShiftInstance.date <= period_end,
        )
        .all()
    )
    shifts = [
        ShiftInstanceInput(
            id=s.id,
            site_id=s.site_id,
            date=s.date,
            start=s.start_datetime,
            end=s.end_datetime,
            category=s.category.value,
            required_physicians=s.required_physicians,
            is_weekend=s.date.weekday() >= 5,
            is_holiday=s.is_holiday,
        )
        for s in shift_rows
    ]

    time_off_rows = (
        db.query(TimeOffRequest)
        .filter(
            TimeOffRequest.org_id == org_id,
            TimeOffRequest.status.in_([RequestStatus.APPROVED, RequestStatus.PENDING]),
            TimeOffRequest.start_date <= period_end,
            TimeOffRequest.end_date >= period_start,
        )
        .all()
    )
    time_off: list[TimeOffBlock] = []
    for r in time_off_rows:
        is_hard = r.priority == RequestPriority.MUST and r.status == RequestStatus.APPROVED
        time_off.append(
            TimeOffBlock(
                physician_id=r.physician_id,
                start_date=r.start_date,
                end_date=r.end_date,
                hard=is_hard,
                weight=1.0 if r.status == RequestStatus.APPROVED else 0.5,
            )
        )

    pref_rows = (
        db.query(ShiftPreference)
        .filter(
            ShiftPreference.org_id == org_id,
            ShiftPreference.effective_start <= period_end,
            ShiftPreference.effective_end >= period_start,
        )
        .all()
    )
    preferences = [
        PreferenceBlock(
            physician_id=p.physician_id,
            start_date=p.effective_start,
            end_date=p.effective_end,
            category=p.category.value,
            level=p.level,
        )
        for p in pref_rows
    ]

    rule_config = RuleConfig(
        max_consecutive_shifts=rules_row.max_consecutive_shifts,
        min_rest_hours=rules_row.min_rest_hours,
        max_nights_in_a_row=rules_row.max_nights_in_a_row,
        weight_unfilled_shift=rules_row.weight_unfilled_shift,
        weight_fairness=rules_row.weight_fairness,
        weight_preference=rules_row.weight_preference,
        weight_preferred_time_off=rules_row.weight_preferred_time_off,
        weight_seniority=rules_row.weight_seniority,
        time_limit_seconds=time_limit_seconds or 30.0,
    )

    return (
        ScheduleInput(
            physicians=physicians,
            shifts=shifts,
            time_off=time_off,
            preferences=preferences,
            rules=rule_config,
        ),
        shift_rows,
    )


def generate_schedule(
    db: Session,
    org_id: str,
    site_id: str,
    period_start: date,
    period_end: date,
    created_by_user_id: str | None = None,
    time_limit_seconds: float | None = None,
) -> ScheduleRun:
    schedule_input, shift_rows = _build_schedule_input(
        db, org_id, site_id, period_start, period_end, time_limit_seconds
    )
    result = solve_schedule(schedule_input)

    run = ScheduleRun(
        org_id=org_id,
        site_id=site_id,
        period_start=period_start,
        period_end=period_end,
        status=ScheduleRunStatus.DRAFT,
        objective_value=result.objective_value,
        solver_status=result.status,
        solve_seconds=result.solve_seconds,
        unfilled_shift_count=len(result.unfilled_shift_ids),
        stats={
            "per_physician": [p.__dict__ for p in result.per_physician],
            "unfilled_shift_ids": result.unfilled_shift_ids,
            "total_shifts": len(shift_rows),
            "total_physicians": len({p for p, _ in result.assignments}),
        },
        created_by_user_id=created_by_user_id,
    )
    db.add(run)
    db.flush()  # obtain run.id

    for physician_id, shift_id in result.assignments:
        db.add(
            Assignment(
                org_id=org_id,
                schedule_run_id=run.id,
                shift_instance_id=shift_id,
                physician_id=physician_id,
            )
        )

    shift_ids = {s.id for s in shift_rows}
    if shift_ids:
        db.query(ShiftInstance).filter(ShiftInstance.id.in_(shift_ids)).update(
            {ShiftInstance.schedule_run_id: run.id}, synchronize_session=False
        )

    db.commit()
    db.refresh(run)
    return run
