"""Lightweight conflict check used when approving a shift swap: this is not
a full re-solve of the schedule, just a targeted check that reassigning one
shift to the claiming physician wouldn't violate the same hard rules the
optimizer itself enforces (double-booking/rest, approved time off, site
eligibility). Cheap enough to run synchronously inside the approval request."""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy.orm import Session

from app.models.enums import RequestPriority, RequestStatus
from app.models.physician import Physician, PhysicianSite
from app.models.requests import TimeOffRequest
from app.models.schedule import Assignment, SchedulingRule
from app.models.shift import ShiftInstance


def find_swap_conflict(
    db: Session, org_id: str, shift: ShiftInstance, candidate_physician_id: str, rules: SchedulingRule
) -> str | None:
    """Returns a human-readable reason the swap can't be approved, or None
    if it's clear."""
    candidate = (
        db.query(Physician)
        .filter(Physician.id == candidate_physician_id, Physician.org_id == org_id)
        .first()
    )
    if candidate is None or not candidate.is_active:
        return "Claiming physician is not an active member of this organization"

    site_restrictions = db.query(PhysicianSite).filter(PhysicianSite.physician_id == candidate.id).count()
    if site_restrictions:
        eligible = (
            db.query(PhysicianSite)
            .filter(PhysicianSite.physician_id == candidate.id, PhysicianSite.site_id == shift.site_id)
            .first()
        )
        if eligible is None:
            return "Claiming physician is not credentialed at this site"

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
        return "Claiming physician has approved time off that day"

    min_rest = candidate.min_rest_hours if candidate.min_rest_hours is not None else rules.min_rest_hours
    window_start = shift.date - timedelta(days=3)
    window_end = shift.date + timedelta(days=3)
    nearby = (
        db.query(ShiftInstance)
        .join(Assignment, Assignment.shift_instance_id == ShiftInstance.id)
        .filter(
            Assignment.physician_id == candidate.id,
            ShiftInstance.date >= window_start,
            ShiftInstance.date <= window_end,
            ShiftInstance.id != shift.id,
        )
        .all()
    )
    for other in nearby:
        if _conflicts(shift, other, min_rest):
            return f"Claiming physician already has a conflicting shift on {other.date}"

    return None


def _conflicts(a: ShiftInstance, b: ShiftInstance, min_rest_hours: float) -> bool:
    first, second = (a, b) if a.start_datetime <= b.start_datetime else (b, a)
    if second.start_datetime < first.end_datetime:
        return True
    gap_hours = (second.start_datetime - first.end_datetime).total_seconds() / 3600.0
    return gap_hours < min_rest_hours
