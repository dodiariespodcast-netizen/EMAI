from datetime import date

from pydantic import BaseModel, Field


class HoursRow(BaseModel):
    physician_id: str
    physician_name: str
    employment_type: str
    shifts: int
    hours: float
    night_hours: float
    weekend_hours: float
    holiday_hours: float
    hourly_rate: float | None
    estimated_cost: float | None


class HoursReport(BaseModel):
    period_start: date
    period_end: date
    rows: list[HoursRow]
    total_shifts: int
    total_hours: float
    total_estimated_cost: float
    # Named explicitly so the cost total is never read as complete when it isn't.
    physicians_missing_rate: list[str] = Field(default_factory=list)


class CoverageReport(BaseModel):
    period_start: date
    period_end: date
    required_slots: int
    staffed_slots: int
    coverage_rate: float
    gaps: list[dict]
