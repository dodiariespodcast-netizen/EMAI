"""Unit tests for the CP-SAT scheduling engine, exercised directly against
the solver's domain model (no database involved)."""

from datetime import date, datetime, timedelta

from app.services.scheduling.domain import (
    PhysicianInput,
    PreferenceBlock,
    RuleConfig,
    ScheduleInput,
    ShiftInstanceInput,
    TimeOffBlock,
)
from app.services.scheduling.engine import solve_schedule

SITE = "site-1"


def _day_shift(shift_id: str, day: date, required: int = 1) -> ShiftInstanceInput:
    return ShiftInstanceInput(
        id=shift_id,
        site_id=SITE,
        date=day,
        start=datetime.combine(day, datetime.min.time()) + timedelta(hours=7),
        end=datetime.combine(day, datetime.min.time()) + timedelta(hours=19),
        category="day",
        required_physicians=required,
        is_weekend=day.weekday() >= 5,
    )


def _night_shift(shift_id: str, day: date, required: int = 1) -> ShiftInstanceInput:
    return ShiftInstanceInput(
        id=shift_id,
        site_id=SITE,
        date=day,
        start=datetime.combine(day, datetime.min.time()) + timedelta(hours=19),
        end=datetime.combine(day, datetime.min.time()) + timedelta(hours=31),  # wraps past midnight
        category="night",
        required_physicians=required,
        is_weekend=day.weekday() >= 5,
    )


def test_empty_period_solves_trivially():
    result = solve_schedule(
        ScheduleInput(physicians=[], shifts=[], time_off=[], preferences=[], rules=RuleConfig())
    )
    assert result.status == "OPTIMAL"
    assert result.assignments == []


def test_full_coverage_when_enough_supply():
    start = date(2026, 1, 5)  # a Monday
    days = [start + timedelta(days=i) for i in range(7)]
    shifts = [_day_shift(f"day-{i}", d) for i, d in enumerate(days)]

    physicians = [
        PhysicianInput(id=f"p{i}", name=f"Doc {i}", fte=1.0, max_shifts_per_period=5)
        for i in range(4)
    ]

    result = solve_schedule(
        ScheduleInput(
            physicians=physicians,
            shifts=shifts,
            time_off=[],
            preferences=[],
            rules=RuleConfig(time_limit_seconds=10),
        )
    )

    assert result.status in ("OPTIMAL", "FEASIBLE")
    assert result.unfilled_shift_ids == []
    assert len(result.assignments) == len(shifts)


def test_hard_time_off_is_never_violated():
    start = date(2026, 1, 5)
    days = [start + timedelta(days=i) for i in range(5)]
    shifts = [_day_shift(f"day-{i}", d) for i, d in enumerate(days)]

    physicians = [PhysicianInput(id="p0", name="Solo Doc", fte=1.0)]
    time_off = [TimeOffBlock(physician_id="p0", start_date=days[2], end_date=days[2], hard=True)]

    result = solve_schedule(
        ScheduleInput(
            physicians=physicians,
            shifts=shifts,
            time_off=time_off,
            preferences=[],
            rules=RuleConfig(time_limit_seconds=10),
        )
    )

    blocked_shift = shifts[2].id
    assigned_shift_ids = {sid for _pid, sid in result.assignments}
    assert blocked_shift not in assigned_shift_ids
    assert blocked_shift in result.unfilled_shift_ids


def test_no_double_booking_or_overlap():
    day = date(2026, 1, 5)
    d_shift = _day_shift("d1", day)
    n_shift = _night_shift("n1", day)  # overlaps the tail of the day shift's rest window

    physicians = [PhysicianInput(id="p0", name="Solo Doc", fte=1.0, min_rest_hours=10)]

    result = solve_schedule(
        ScheduleInput(
            physicians=physicians,
            shifts=[d_shift, n_shift],
            time_off=[],
            preferences=[],
            rules=RuleConfig(time_limit_seconds=10),
        )
    )
    assigned_shift_ids = [sid for _pid, sid in result.assignments]
    # only one physician exists and can't legally work both -> at most one shift filled
    assert len(assigned_shift_ids) <= 1


def test_max_consecutive_shifts_is_respected():
    start = date(2026, 1, 5)
    days = [start + timedelta(days=i) for i in range(10)]
    shifts = [_day_shift(f"day-{i}", d) for i, d in enumerate(days)]

    physicians = [PhysicianInput(id="p0", name="Solo Doc", fte=1.0, max_consecutive_shifts=3)]

    result = solve_schedule(
        ScheduleInput(
            physicians=physicians,
            shifts=shifts,
            time_off=[],
            preferences=[],
            rules=RuleConfig(time_limit_seconds=10),
        )
    )

    assigned_days = sorted(
        s.date for s in shifts if any(sid == s.id for _pid, sid in result.assignments)
    )
    # verify no run of more than 3 consecutive calendar days
    run_len = 1
    for prev, cur in zip(assigned_days, assigned_days[1:]):
        if (cur - prev).days == 1:
            run_len += 1
            assert run_len <= 3
        else:
            run_len = 1


def test_preferences_bias_assignment_toward_the_physician_who_wants_it():
    start = date(2026, 1, 5)
    nights = [_night_shift(f"night-{i}", start + timedelta(days=i)) for i in range(5)]

    night_lover = PhysicianInput(id="lover", name="Night Lover", fte=1.0, night_preference=2)
    night_hater = PhysicianInput(id="hater", name="Night Hater", fte=1.0, night_preference=-2)

    result = solve_schedule(
        ScheduleInput(
            physicians=[night_lover, night_hater],
            shifts=nights,
            time_off=[],
            preferences=[],
            rules=RuleConfig(time_limit_seconds=10, weight_fairness=0.5),
        )
    )

    lover_count = sum(1 for pid, _sid in result.assignments if pid == "lover")
    hater_count = sum(1 for pid, _sid in result.assignments if pid == "hater")
    assert lover_count > hater_count


def test_fairness_balances_workload_by_fte():
    start = date(2026, 1, 5)
    days = [start + timedelta(days=i) for i in range(12)]
    shifts = [_day_shift(f"day-{i}", d) for i, d in enumerate(days)]

    full_time = PhysicianInput(id="full", name="Full Time", fte=1.0)
    half_time = PhysicianInput(id="half", name="Half Time", fte=0.5)

    result = solve_schedule(
        ScheduleInput(
            physicians=[full_time, half_time],
            shifts=shifts,
            time_off=[],
            preferences=[],
            rules=RuleConfig(time_limit_seconds=10),
        )
    )

    full_count = sum(1 for pid, _sid in result.assignments if pid == "full")
    half_count = sum(1 for pid, _sid in result.assignments if pid == "half")
    assert full_count > half_count
