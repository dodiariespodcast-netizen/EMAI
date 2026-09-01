"""Targeted conflict check for a single assignment change -- used both when
approving a shift swap and when a scheduler hand-edits a generated schedule.

This is not a full re-solve. It verifies that giving one shift to one
physician wouldn't break the same *hard* rules the optimizer enforces
(double-booking/rest, approved must-off time, site eligibility, active
roster membership), which is cheap enough to run synchronously inside the
request. Soft concerns -- fairness, preferences -- are deliberately not
enforced here: a human overriding the solver is allowed to be unfair, they
just aren't allowed to be unsafe or illegal.
"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy.orm import Session

from app.models.enums import RequestPriority, RequestStatus
from app.models.physician import Physician, PhysicianSite
from app.models.requests import TimeOffRequest
from app.models.schedule import Assignment, SchedulingRule
from app.models.shift import ShiftInstance

# How far either side of the target date to look for overlapping/insufficient-
# rest shifts. Three days comfortably covers any rest window a real rule set
# uses while keeping the query small.
_CONFLICT_WINDOW_DAYS = 3


def find_assignment_conflict(
    db: Session,
    org_id: str,
    shift: ShiftInstance,
    candidate_physician_id: str,
    rules: SchedulingRule,
    exclude_assignment_id: str | None = None,
) -> str | None:
    """Returns a human-readable reason this physician can't take this shift,
    or None if it's clear.

    `exclude_assignment_id` skips one existing assignment when checking for
    clashes -- used when reassigning a shift that the physician is already
    (about to stop) holding.
    """
    candidate = (
        db.query(Physician)
        .filter(Physician.id == candidate_physician_id, Physician.org_id == org_id)
        .first()
    )
    if candidate is None or not candidate.is_active:
        return "That physician is not an active member of this organization"

    site_restrictions = db.query(PhysicianSite).filter(PhysicianSite.physician_id == candidate.id).count()
    if site_restrictions:
        eligible = (
            db.query(PhysicianSite)
            .filter(PhysicianSite.physician_id == candidate.id, PhysicianSite.site_id == shift.site_id)
            .first()
        )
        if eligible is None:
            return f"{candidate.first_name} {candidate.last_name} is not credentialed at this site"

    already_on_this_shift = (
        db.query(Assignment)
        .filter(Assignment.shift_instance_id == shift.id, Assignment.physician_id == candidate.id)
    )
    if exclude_assignment_id:
        already_on_this_shift = already_on_this_shift.filter(Assignment.id != exclude_assignment_id)
    if already_on_this_shift.first() is not None:
        return f"{candidate.first_name} {candidate.last_name} is already on this shift"

    hard_time_off = (
        db.query(TimeOffRequest)
        .filter(
            TimeOffRequest.physician_id == candidate.id,
            TimeOffRequest.status == RequestStatus.APPROVED,
            TimeOffRequest.priority == RequestPriority.MUST,
            TimeOffRequest.start_date <= shift.date,
            TimeOffRequest.end_date >= shift.date,
        )
        .first()
    )
    if hard_time_off is not None:
        return f"{candidate.first_name} {candidate.last_name} has approved time off that day"

    min_rest = candidate.min_rest_hours if candidate.min_rest_hours is not None else rules.min_rest_hours
    nearby_q = (
        db.query(ShiftInstance, Assignment.id)
        .join(Assignment, Assignment.shift_instance_id == ShiftInstance.id)
        .filter(
            Assignment.physician_id == candidate.id,
            ShiftInstance.date >= shift.date - timedelta(days=_CONFLICT_WINDOW_DAYS),
            ShiftInstance.date <= shift.date + timedelta(days=_CONFLICT_WINDOW_DAYS),
            ShiftInstance.id != shift.id,
        )
    )
    if exclude_assignment_id:
        nearby_q = nearby_q.filter(Assignment.id != exclude_assignment_id)

    for other, _assignment_id in nearby_q.all():
        if _conflicts(shift, other, min_rest):
            return (
                f"{candidate.first_name} {candidate.last_name} already has a shift on {other.date} "
                f"that overlaps or leaves less than {min_rest:g}h rest"
            )

    return None


# Kept under its original name for the swap-approval call site, where the
# wording "swap conflict" is what the caller is actually asking about.
find_swap_conflict = find_assignment_conflict


def _conflicts(a: ShiftInstance, b: ShiftInstance, min_rest_hours: float) -> bool:
    first, second = (a, b) if a.start_datetime <= b.start_datetime else (b, a)
    if second.start_datetime < first.end_datetime:
        return True
    gap_hours = (second.start_datetime - first.end_datetime).total_seconds() / 3600.0
    return gap_hours < min_rest_hours
