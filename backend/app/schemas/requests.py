from datetime import date

from pydantic import BaseModel, Field

from app.models.enums import (
    RequestPriority,
    RequestStatus,
    ShiftCategory,
    TimeOffType,
)


class TimeOffRequestCreate(BaseModel):
    physician_id: str
    start_date: date
    end_date: date
    request_type: TimeOffType = TimeOffType.PERSONAL
    priority: RequestPriority = RequestPriority.PREFERRED
    reason: str | None = None


class TimeOffRequestFromText(BaseModel):
    """Natural-language intake, e.g. 'I need the week of Dec 22-29 off for
    vacation, it's important' -- parsed into structured fields by the AI
    layer (falls back to a rule-based parser if no LLM key is configured)."""

    physician_id: str
    text: str = Field(min_length=3)


class TimeOffRequestUpdate(BaseModel):
    status: RequestStatus


class TimeOffRequestRead(BaseModel):
    id: str
    org_id: str
    physician_id: str
    start_date: date
    end_date: date
    request_type: TimeOffType
    priority: RequestPriority
    status: RequestStatus
    reason: str | None
    raw_text: str | None

    model_config = {"from_attributes": True}


class ShiftPreferenceCreate(BaseModel):
    physician_id: str
    effective_start: date
    effective_end: date
    category: ShiftCategory = ShiftCategory.NIGHT
    level: int = Field(ge=-2, le=2)
    note: str | None = None


class ShiftPreferenceRead(BaseModel):
    id: str
    org_id: str
    physician_id: str
    effective_start: date
    effective_end: date
    category: ShiftCategory
    level: int
    note: str | None

    model_config = {"from_attributes": True}
