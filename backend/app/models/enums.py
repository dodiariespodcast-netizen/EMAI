import enum


class UserRole(str, enum.Enum):
    OWNER = "owner"
    ADMIN = "admin"
    SCHEDULER = "scheduler"
    PHYSICIAN = "physician"


class ShiftCategory(str, enum.Enum):
    DAY = "day"
    NIGHT = "night"
    SWING = "swing"
    ADMIN = "admin"


class TimeOffType(str, enum.Enum):
    VACATION = "vacation"
    CME = "cme"
    PERSONAL = "personal"
    SICK = "sick"
    OTHER = "other"


class RequestPriority(str, enum.Enum):
    """MUST requests are treated as a hard constraint by the solver (the
    physician will never be scheduled against them). PREFERRED requests are a
    soft constraint the solver tries to honor, weighted against everyone
    else's preferences and fairness."""

    MUST = "must"
    PREFERRED = "preferred"


class RequestStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    WITHDRAWN = "withdrawn"


class PreferenceLevel(int, enum.Enum):
    STRONGLY_AVOID = -2
    AVOID = -1
    NEUTRAL = 0
    PREFER = 1
    STRONGLY_PREFER = 2


class ScheduleRunStatus(str, enum.Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class AssignmentStatus(str, enum.Enum):
    ASSIGNED = "assigned"
    SWAPPED = "swapped"
    DROPPED = "dropped"


class SwapStatus(str, enum.Enum):
    OPEN = "open"  # posted to the marketplace, unclaimed
    CLAIMED = "claimed"  # another physician wants it, awaiting scheduler approval
    APPROVED = "approved"  # scheduler approved; the assignment has been reassigned
    REJECTED = "rejected"
    CANCELLED = "cancelled"  # withdrawn by the offering physician before it was claimed


class CredentialType(str, enum.Enum):
    STATE_LICENSE = "state_license"
    DEA = "dea"
    BOARD_CERTIFICATION = "board_certification"
    MALPRACTICE_INSURANCE = "malpractice_insurance"
    ACLS = "acls"
    BLS = "bls"
    PALS = "pals"
    HOSPITAL_PRIVILEGES = "hospital_privileges"
    OTHER = "other"


class EmploymentType(str, enum.Enum):
    """Distinguishes an EM group's own employed physicians from locums/
    contract physicians -- the core distinction a locums agency's roster
    is organized around, and something an EM group also needs for its own
    moonlighter/PRN pool."""

    EMPLOYED = "employed"
    LOCUMS = "locums"
    CONTRACT = "contract"
    MOONLIGHTER = "moonlighter"
