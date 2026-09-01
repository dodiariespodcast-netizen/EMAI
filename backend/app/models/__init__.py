"""Import every model module so they register on Base.metadata before
init_db()/Alembic autogenerate runs, and re-export the ORM classes for
convenient `from app.models import Physician` style imports elsewhere."""

from app.models.physician import Credential, Physician, PhysicianSite
from app.models.requests import ShiftPreference, TimeOffRequest
from app.models.schedule import Assignment, ScheduleRun, SchedulingRule, ShiftSwapRequest
from app.models.shift import ShiftInstance, ShiftType
from app.models.tenancy import (
    AuditLog,
    OAuthIdentity,
    Organization,
    PasswordResetToken,
    Site,
    User,
)

__all__ = [
    "Organization",
    "Site",
    "User",
    "OAuthIdentity",
    "AuditLog",
    "PasswordResetToken",
    "Physician",
    "PhysicianSite",
    "Credential",
    "ShiftType",
    "ShiftInstance",
    "TimeOffRequest",
    "ShiftPreference",
    "SchedulingRule",
    "ScheduleRun",
    "Assignment",
    "ShiftSwapRequest",
]
