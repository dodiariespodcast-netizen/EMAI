"""Solver-facing domain model.

Deliberately decoupled from the SQLAlchemy ORM: the optimizer only knows
about these plain dataclasses, which keeps it unit-testable without a
database and makes it straightforward to lift into a standalone service
later if scheduling load ever needs to scale independently of the API.
"""

from dataclasses import dataclass, field
from datetime import date, datetime


@dataclass(frozen=True)
class PhysicianInput:
    id: str
    name: str
    fte: float = 1.0
    seniority_years: float = 0.0
    night_preference: int = 0  # -2..2
    weekend_preference: int = 0
    holiday_preference: int = 0
    eligible_site_ids: frozenset[str] = field(default_factory=frozenset)
    max_consecutive_shifts: int | None = None
    min_rest_hours: float | None = None
    max_shifts_per_period: int | None = None


@dataclass(frozen=True)
class ShiftInstanceInput:
    id: str
    site_id: str
    date: date
    start: datetime
    end: datetime
    category: str  # "day" | "night" | "swing" | "admin"
    required_physicians: int = 1
    is_weekend: bool = False
    is_holiday: bool = False


@dataclass(frozen=True)
class TimeOffBlock:
    physician_id: str
    start_date: date
    end_date: date
    hard: bool  # True: MUST + APPROVED -> solver treats as unbreakable
    weight: float = 1.0  # soft-request strength, used when hard=False


@dataclass(frozen=True)
class PreferenceBlock:
    physician_id: str
    start_date: date
    end_date: date
    category: str  # day | night | weekend | holiday
    level: int  # -2..2


@dataclass
class RuleConfig:
    max_consecutive_shifts: int = 5
    min_rest_hours: float = 10.0
    max_nights_in_a_row: int = 4
    weight_unfilled_shift: float = 1000.0
    weight_fairness: float = 8.0
    weight_preference: float = 3.0
    weight_preferred_time_off: float = 6.0
    weight_seniority: float = 1.0  # 0 disables seniority-weighted preference skew
    time_limit_seconds: float = 30.0


@dataclass
class ScheduleInput:
    physicians: list[PhysicianInput]
    shifts: list[ShiftInstanceInput]
    time_off: list[TimeOffBlock]
    preferences: list[PreferenceBlock]
    rules: RuleConfig


@dataclass
class PhysicianSummary:
    physician_id: str
    total_shifts: int
    target_shifts: float
    night_shifts: int
    weekend_shifts: int
    holiday_shifts: int


@dataclass
class SolveResult:
    status: str  # OPTIMAL | FEASIBLE | INFEASIBLE | UNKNOWN | MODEL_INVALID
    objective_value: float | None
    assignments: list[tuple[str, str]]  # (physician_id, shift_instance_id)
    unfilled_shift_ids: list[str]
    solve_seconds: float
    per_physician: list[PhysicianSummary]
