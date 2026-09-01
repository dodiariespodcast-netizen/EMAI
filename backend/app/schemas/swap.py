from pydantic import BaseModel, Field

from app.models.enums import SwapStatus


class ShiftSwapCreate(BaseModel):
    assignment_id: str
    target_physician_id: str | None = None  # None = open to anyone
    note: str | None = None


class ShiftSwapRead(BaseModel):
    id: str
    org_id: str
    assignment_id: str
    offering_physician_id: str
    target_physician_id: str | None
    claimed_by_physician_id: str | None
    status: SwapStatus
    note: str | None

    model_config = {"from_attributes": True}


class ShiftSwapRejection(BaseModel):
    reason: str | None = None


class ShiftSwapClaim(BaseModel):
    physician_id: str
