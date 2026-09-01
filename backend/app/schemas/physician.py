from pydantic import BaseModel, EmailStr, Field

from app.models.enums import EmploymentType


class PhysicianCreate(BaseModel):
    first_name: str
    last_name: str
    email: EmailStr
    credentials: str = "MD"
    fte: float = Field(default=1.0, ge=0.0, le=1.0)
    seniority_years: float = 0.0
    night_preference: int = Field(default=0, ge=-2, le=2)
    weekend_preference: int = Field(default=0, ge=-2, le=2)
    holiday_preference: int = Field(default=0, ge=-2, le=2)
    max_consecutive_shifts: int | None = None
    min_rest_hours: float | None = None
    max_shifts_per_period: int | None = None
    employment_type: EmploymentType = EmploymentType.EMPLOYED
    hourly_rate: float | None = Field(default=None, ge=0)
    site_ids: list[str] = Field(default_factory=list)


class PhysicianUpdate(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    email: EmailStr | None = None
    credentials: str | None = None
    is_active: bool | None = None
    fte: float | None = Field(default=None, ge=0.0, le=1.0)
    seniority_years: float | None = None
    night_preference: int | None = Field(default=None, ge=-2, le=2)
    weekend_preference: int | None = Field(default=None, ge=-2, le=2)
    holiday_preference: int | None = Field(default=None, ge=-2, le=2)
    max_consecutive_shifts: int | None = None
    min_rest_hours: float | None = None
    max_shifts_per_period: int | None = None
    employment_type: EmploymentType | None = None
    hourly_rate: float | None = Field(default=None, ge=0)
    site_ids: list[str] | None = None


class PhysicianPreferencesUpdate(BaseModel):
    """The subset of a physician's own record a physician (not just a
    scheduler) is allowed to self-edit -- their standing shift preferences.
    Everything else on Physician (FTE, employment type, pay rate, hard
    rule overrides) stays scheduler-only via PhysicianUpdate."""

    night_preference: int | None = Field(default=None, ge=-2, le=2)
    weekend_preference: int | None = Field(default=None, ge=-2, le=2)
    holiday_preference: int | None = Field(default=None, ge=-2, le=2)


class PhysicianRead(BaseModel):
    id: str
    org_id: str
    first_name: str
    last_name: str
    email: EmailStr
    credentials: str
    is_active: bool
    fte: float
    seniority_years: float
    night_preference: int
    weekend_preference: int
    holiday_preference: int
    max_consecutive_shifts: int | None
    min_rest_hours: float | None
    max_shifts_per_period: int | None
    employment_type: EmploymentType
    hourly_rate: float | None
    calendar_token: str
    site_ids: list[str] = Field(default_factory=list)

    model_config = {"from_attributes": True}
