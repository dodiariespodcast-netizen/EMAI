from datetime import date, datetime, time

from pydantic import BaseModel, Field

from app.models.enums import ShiftCategory


class SiteCreate(BaseModel):
    name: str
    timezone: str = "UTC"


class SiteRead(BaseModel):
    id: str
    org_id: str
    name: str
    timezone: str

    model_config = {"from_attributes": True}


class ShiftTypeCreate(BaseModel):
    site_id: str
    name: str
    category: ShiftCategory = ShiftCategory.DAY
    start_time: time
    end_time: time
    duration_hours: float = Field(gt=0, le=24)
    required_physicians: int = Field(default=1, ge=1)


class ShiftTypeRead(BaseModel):
    id: str
    org_id: str
    site_id: str
    name: str
    category: ShiftCategory
    start_time: time
    end_time: time
    duration_hours: float
    required_physicians: int

    model_config = {"from_attributes": True}


class ShiftInstanceGenerate(BaseModel):
    """Bulk-generate shift instances for a shift type over a date range,
    one per day (typical ED pattern of a daily recurring shift)."""

    shift_type_id: str
    start_date: date
    end_date: date
    holiday_dates: list[date] = Field(default_factory=list)


class ShiftInstanceCreate(BaseModel):
    shift_type_id: str
    date: date
    required_physicians: int | None = None
    is_holiday: bool = False


class ShiftInstanceRead(BaseModel):
    id: str
    org_id: str
    site_id: str
    shift_type_id: str
    schedule_run_id: str | None
    date: date
    start_datetime: datetime
    end_datetime: datetime
    category: ShiftCategory
    required_physicians: int
    is_holiday: bool

    model_config = {"from_attributes": True}


class EligiblePhysician(BaseModel):
    """One candidate for an open shift, with the reason they can't take it
    when that's the case -- the picker shows conflicted physicians greyed out
    with the reason rather than hiding them, since a scheduler sometimes needs
    to override anyway."""

    physician_id: str
    name: str
    employment_type: str
    conflict: str | None = None
    assigned_shifts_in_period: int = 0
