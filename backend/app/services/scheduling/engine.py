"""Constraint-programming scheduling engine.

This is the "AI" in the sense that matters for a scheduling product: a
constraint-satisfaction / combinatorial-optimization solver (Google
OR-Tools CP-SAT) that treats coverage requirements as hard constraints and
everyone's preferences, seniority, and fairness as a weighted objective it
maximizes. It is deterministic and explainable -- important for a product
that has to justify its output to a room of physicians -- unlike a pure
LLM-generated schedule, which cannot reliably guarantee hard constraints
like "never double-book a physician" or "never violate an approved
time-off request". The natural-language layer (see app/services/ai) sits
on top of this for request intake and explaining results in plain English.

Scale note: CP-SAT comfortably handles the problem sizes this domain
produces (tens of physicians x hundreds of shift instances per month --
low tens of thousands of decision variables) within the configured time
limit, returning the best feasible solution found even if the search is
stopped before proving optimality.
"""

from __future__ import annotations

import time
from collections import defaultdict
from datetime import date, timedelta

from ortools.sat.python import cp_model

from app.services.scheduling.domain import (
    PhysicianInput,
    PhysicianSummary,
    ScheduleInput,
    ShiftInstanceInput,
    SolveResult,
)

# CP-SAT requires integer coefficients; we scale float weights/preferences
# by this factor before rounding so the objective retains precision.
_SCALE = 100


def _is_hard_blocked(phys_id: str, shift: ShiftInstanceInput, hard_blocks: dict[str, list[tuple[date, date]]]) -> bool:
    for start, end in hard_blocks.get(phys_id, []):
        if start <= shift.date <= end:
            return True
    return False


def _rest_violation(a: ShiftInstanceInput, b: ShiftInstanceInput, min_rest_hours: float) -> bool:
    """True if working both a and b would overlap or leave less than
    min_rest_hours between the earlier shift's end and the later shift's start."""
    if a.start > b.start:
        a, b = b, a
    if b.start < a.end:  # overlap
        return True
    gap_hours = (b.start - a.end).total_seconds() / 3600.0
    return gap_hours < min_rest_hours


def solve_schedule(inp: ScheduleInput) -> SolveResult:
    started = time.monotonic()
    rules = inp.rules
    model = cp_model.CpModel()

    physicians = inp.physicians
    shifts = inp.shifts
    phys_by_id = {p.id: p for p in physicians}
    shift_by_id = {s.id: s for s in shifts}

    if not shifts:
        return SolveResult(
            status="OPTIMAL",
            objective_value=0.0,
            assignments=[],
            unfilled_shift_ids=[],
            solve_seconds=time.monotonic() - started,
            per_physician=[],
        )

    # ---- hard time-off blocks, keyed by physician ----
    hard_blocks: dict[str, list[tuple[date, date]]] = defaultdict(list)
    soft_time_off: dict[tuple[str, date], float] = {}
    for block in inp.time_off:
        if block.hard:
            hard_blocks[block.physician_id].append((block.start_date, block.end_date))
        else:
            d = block.start_date
            while d <= block.end_date:
                soft_time_off[(block.physician_id, d)] = max(
                    soft_time_off.get((block.physician_id, d), 0.0), block.weight
                )
                d += timedelta(days=1)

    # ---- preference lookup: (physician_id, category) -> most recent level covering the date ----
    def preference_level(physician: PhysicianInput, shift: ShiftInstanceInput) -> int:
        level = 0
        matched = False
        for pref in inp.preferences:
            if pref.physician_id != physician.id:
                continue
            if pref.category != shift.category and not (
                pref.category == "weekend" and shift.is_weekend
            ) and not (pref.category == "holiday" and shift.is_holiday):
                continue
            if pref.start_date <= shift.date <= pref.end_date:
                level = pref.level
                matched = True
        if not matched:
            if shift.category == "night":
                level = physician.night_preference
            elif shift.is_weekend:
                level = physician.weekend_preference
            if shift.is_holiday:
                level = max(level, physician.holiday_preference, key=abs) if level else physician.holiday_preference
        return level

    # ---- decision variables: x[physician_id, shift_id] ----
    x: dict[tuple[str, str], cp_model.IntVar] = {}
    eligible_physicians_for_shift: dict[str, list[str]] = defaultdict(list)

    for shift in shifts:
        for physician in physicians:
            if physician.eligible_site_ids and shift.site_id not in physician.eligible_site_ids:
                continue
            if _is_hard_blocked(physician.id, shift, hard_blocks):
                continue
            var = model.NewBoolVar(f"x_{physician.id}_{shift.id}")
            x[(physician.id, shift.id)] = var
            eligible_physicians_for_shift[shift.id].append(physician.id)

    # ---- coverage with shortfall slack (heavily penalized, never infeasible) ----
    shortfall: dict[str, cp_model.IntVar] = {}
    for shift in shifts:
        assigned_vars = [x[(pid, shift.id)] for pid in eligible_physicians_for_shift[shift.id]]
        slack = model.NewIntVar(0, shift.required_physicians, f"short_{shift.id}")
        shortfall[shift.id] = slack
        model.Add(sum(assigned_vars) + slack == shift.required_physicians)

    # ---- no double-booking / rest-window conflicts ----
    shifts_sorted = sorted(shifts, key=lambda s: s.start)
    for physician in physicians:
        min_rest = physician.min_rest_hours if physician.min_rest_hours is not None else rules.min_rest_hours
        n = len(shifts_sorted)
        for i in range(n):
            s1 = shifts_sorted[i]
            v1 = x.get((physician.id, s1.id))
            if v1 is None:
                continue
            for j in range(i + 1, n):
                s2 = shifts_sorted[j]
                # shifts are sorted by start; once s2 starts well past s1's
                # end + max plausible rest window we can stop scanning
                if (s2.start - s1.end).total_seconds() / 3600.0 > 72:
                    break
                v2 = x.get((physician.id, s2.id))
                if v2 is None:
                    continue
                if _rest_violation(s1, s2, min_rest):
                    model.Add(v1 + v2 <= 1)

    # ---- per-physician-per-day "worked" and "worked a night" indicators ----
    shifts_by_day: dict[date, list[ShiftInstanceInput]] = defaultdict(list)
    for shift in shifts:
        shifts_by_day[shift.date].append(shift)
    all_days = sorted(shifts_by_day.keys())

    worked_day: dict[tuple[str, date], cp_model.IntVar] = {}
    worked_night: dict[tuple[str, date], cp_model.IntVar] = {}
    for physician in physicians:
        for day in all_days:
            day_vars = [x[(physician.id, s.id)] for s in shifts_by_day[day] if (physician.id, s.id) in x]
            if not day_vars:
                continue
            wd = model.NewBoolVar(f"wd_{physician.id}_{day}")
            model.AddMaxEquality(wd, day_vars)
            worked_day[(physician.id, day)] = wd

            night_vars = [
                x[(physician.id, s.id)]
                for s in shifts_by_day[day]
                if s.category == "night" and (physician.id, s.id) in x
            ]
            if night_vars:
                wn = model.NewBoolVar(f"wn_{physician.id}_{day}")
                model.AddMaxEquality(wn, night_vars)
                worked_night[(physician.id, day)] = wn

    # ---- max consecutive working days ----
    for physician in physicians:
        max_consec = physician.max_consecutive_shifts or rules.max_consecutive_shifts
        window = max_consec + 1
        if len(all_days) < window:
            continue
        for start_idx in range(len(all_days) - window + 1):
            window_days = all_days[start_idx : start_idx + window]
            vars_in_window = [worked_day[(physician.id, d)] for d in window_days if (physician.id, d) in worked_day]
            if len(vars_in_window) == window:
                model.Add(sum(vars_in_window) <= max_consec)

    # ---- max consecutive nights ----
    for physician in physicians:
        max_nights = rules.max_nights_in_a_row
        window = max_nights + 1
        if len(all_days) < window:
            continue
        for start_idx in range(len(all_days) - window + 1):
            window_days = all_days[start_idx : start_idx + window]
            vars_in_window = [
                worked_night[(physician.id, d)] for d in window_days if (physician.id, d) in worked_night
            ]
            if len(vars_in_window) == window:
                model.Add(sum(vars_in_window) <= max_nights)

    # ---- per-period cap ----
    for physician in physicians:
        cap = physician.max_shifts_per_period
        if cap is None:
            continue
        assigned = [v for (pid, _sid), v in x.items() if pid == physician.id]
        if assigned:
            model.Add(sum(assigned) <= cap)

    # ---- fairness targets (proportional to FTE) ----
    total_fte = sum(p.fte for p in physicians) or 1.0
    total_slots = sum(s.required_physicians for s in shifts)
    total_night_slots = sum(s.required_physicians for s in shifts if s.category == "night")
    total_weekend_slots = sum(s.required_physicians for s in shifts if s.is_weekend)

    total_count: dict[str, cp_model.IntVar] = {}
    night_count: dict[str, cp_model.IntVar] = {}
    weekend_count: dict[str, cp_model.IntVar] = {}
    fairness_terms: list[cp_model.LinearExpr] = []

    for physician in physicians:
        assigned = [v for (pid, _sid), v in x.items() if pid == physician.id]
        max_possible = len(assigned) if assigned else 0
        tc = model.NewIntVar(0, max_possible, f"total_{physician.id}")
        model.Add(tc == sum(assigned)) if assigned else model.Add(tc == 0)
        total_count[physician.id] = tc

        night_assigned = [
            v for (pid, sid), v in x.items() if pid == physician.id and shift_by_id[sid].category == "night"
        ]
        nc = model.NewIntVar(0, len(night_assigned), f"night_{physician.id}")
        model.Add(nc == sum(night_assigned)) if night_assigned else model.Add(nc == 0)
        night_count[physician.id] = nc

        weekend_assigned = [
            v for (pid, sid), v in x.items() if pid == physician.id and shift_by_id[sid].is_weekend
        ]
        wc = model.NewIntVar(0, len(weekend_assigned), f"wknd_{physician.id}")
        model.Add(wc == sum(weekend_assigned)) if weekend_assigned else model.Add(wc == 0)
        weekend_count[physician.id] = wc

        fair_share = physician.fte / total_fte
        target_total = round(fair_share * total_slots * _SCALE)
        target_night = round(fair_share * total_night_slots * _SCALE)
        target_weekend = round(fair_share * total_weekend_slots * _SCALE)

        dev_total = model.NewIntVar(0, max(1, total_slots) * _SCALE, f"devt_{physician.id}")
        model.Add(dev_total >= tc * _SCALE - target_total)
        model.Add(dev_total >= target_total - tc * _SCALE)

        dev_night = model.NewIntVar(0, max(1, total_night_slots) * _SCALE, f"devn_{physician.id}")
        model.Add(dev_night >= nc * _SCALE - target_night)
        model.Add(dev_night >= target_night - nc * _SCALE)

        dev_weekend = model.NewIntVar(0, max(1, total_weekend_slots) * _SCALE, f"devw_{physician.id}")
        model.Add(dev_weekend >= wc * _SCALE - target_weekend)
        model.Add(dev_weekend >= target_weekend - wc * _SCALE)

        fairness_terms.extend([dev_total, dev_night, dev_weekend])

    # ---- objective ----
    objective_terms: list[cp_model.LinearExpr] = []

    # 1) heavily penalize unfilled shifts
    for shift in shifts:
        objective_terms.append(-shortfall[shift.id] * round(rules.weight_unfilled_shift * _SCALE))

    # 2) reward preference satisfaction (seniority can amplify a physician's weight)
    for (pid, sid), var in x.items():
        physician = phys_by_id[pid]
        shift = shift_by_id[sid]
        level = preference_level(physician, shift)
        if level == 0:
            continue
        seniority_mult = 1.0 + rules.weight_seniority * min(physician.seniority_years, 30) / 30.0
        coeff = round(level * rules.weight_preference * seniority_mult * _SCALE)
        objective_terms.append(var * coeff)

    # 3) reward honoring preferred (soft) time-off requests by *not* scheduling that day
    #    modeled as a penalty on assigning a shift on a day the physician asked off
    for shift in shifts:
        for pid in eligible_physicians_for_shift[shift.id]:
            weight = soft_time_off.get((pid, shift.date))
            if weight:
                coeff = round(weight * rules.weight_preferred_time_off * _SCALE)
                objective_terms.append(-x[(pid, shift.id)] * coeff)

    # 4) fairness penalty
    for term in fairness_terms:
        objective_terms.append(-term * round(rules.weight_fairness))

    model.Maximize(sum(objective_terms))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = rules.time_limit_seconds
    solver.parameters.num_search_workers = 8
    status = solver.Solve(model)

    status_name = solver.StatusName(status)
    elapsed = time.monotonic() - started

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return SolveResult(
            status=status_name,
            objective_value=None,
            assignments=[],
            unfilled_shift_ids=[s.id for s in shifts],
            solve_seconds=elapsed,
            per_physician=[],
        )

    assignments: list[tuple[str, str]] = [
        (pid, sid) for (pid, sid), var in x.items() if solver.Value(var) == 1
    ]
    unfilled = [s.id for s in shifts if solver.Value(shortfall[s.id]) > 0]

    per_physician = []
    for physician in physicians:
        per_physician.append(
            PhysicianSummary(
                physician_id=physician.id,
                total_shifts=solver.Value(total_count[physician.id]),
                target_shifts=round(physician.fte / total_fte * total_slots, 2),
                night_shifts=solver.Value(night_count[physician.id]),
                weekend_shifts=solver.Value(weekend_count[physician.id]),
                holiday_shifts=sum(
                    1
                    for (pid, sid) in assignments
                    if pid == physician.id and shift_by_id[sid].is_holiday
                ),
            )
        )

    return SolveResult(
        status=status_name,
        objective_value=solver.ObjectiveValue() / _SCALE,
        assignments=assignments,
        unfilled_shift_ids=unfilled,
        solve_seconds=elapsed,
        per_physician=per_physician,
    )
