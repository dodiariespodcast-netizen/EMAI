from datetime import date, datetime

from pydantic import BaseModel, Field

from app.models.enums import ScheduleRunStatus


class SchedulingRuleUpdate(BaseModel):
    max_consecutive_shifts: int | None = Field(default=None, ge=1, le=14)
    min_rest_hours: float | None = Field(default=None, ge=0, le=48)
    max_nights_in_a_row: int | None = Field(default=None, ge=1, le=14)
    weight_unfilled_shift: float | None = None
    weight_fairness: float | None = None
    weight_preference: float | None = None
    weight_preferred_time_off: float | None = None
    weight_seniority: float | None = None


class SchedulingRuleRead(BaseModel):
    org_id: str
    max_consecutive_shifts: int
    min_rest_hours: float
    max_nights_in_a_row: int
    weight_unfilled_shift: float
    weight_fairness: float
    weight_preference: float
    weight_preferred_time_off: float
    weight_seniority: float

    model_config = {"from_attributes": True}


class ScheduleGenerateRequest(BaseModel):
    site_id: str
    period_start: date
    period_end: date
    time_limit_seconds: float | None = Field(default=None, gt=0, le=300)
    generate_ai_summary: bool = True


class AssignmentRead(BaseModel):
    id: str
    shift_instance_id: str
    physician_id: str
    status: str

    model_config = {"from_attributes": True}


class AssignmentDetail(AssignmentRead):
    """Assignment with the shift/site fields a client needs to render it
    (date, time, category, site) denormalized in, so callers like the
    shift-swap marketplace or a "my schedule" view don't have to separately
    resolve shift instances and schedule runs themselves."""

    schedule_run_id: str
    schedule_run_status: ScheduleRunStatus
    site_id: str
    site_name: str
    date: date
    start_datetime: datetime
    end_datetime: datetime
    category: str
    shift_type_name: str


class ScheduleRunRead(BaseModel):
    id: str
    org_id: str
    site_id: str
    period_start: date
    period_end: date
    status: ScheduleRunStatus
    objective_value: float | None
    solver_status: str | None
    solve_seconds: float | None
    unfilled_shift_count: int
    stats: dict
    ai_summary: str | None

    model_config = {"from_attributes": True}


class ScheduleRunDetail(ScheduleRunRead):
    assignments: list[AssignmentRead] = Field(default_factory=list)


class FairnessRow(BaseModel):
    physician_id: str
    physician_name: str
    total_shifts: int
    target_shifts: float
    night_shifts: int
    weekend_shifts: int
    holiday_shifts: int
    preferred_requests_granted: int
    preferred_requests_total: int
