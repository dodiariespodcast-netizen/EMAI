from datetime import date

from pydantic import BaseModel, Field

from app.models.enums import CredentialType


class CredentialCreate(BaseModel):
    physician_id: str
    credential_type: CredentialType = CredentialType.STATE_LICENSE
    identifier: str | None = None
    issuing_state: str | None = Field(default=None, max_length=2)
    issued_date: date | None = None
    expires_on: date | None = None
    note: str | None = None


class CredentialUpdate(BaseModel):
    identifier: str | None = None
    issuing_state: str | None = Field(default=None, max_length=2)
    issued_date: date | None = None
    expires_on: date | None = None
    note: str | None = None


class CredentialRead(BaseModel):
    id: str
    org_id: str
    physician_id: str
    credential_type: CredentialType
    identifier: str | None
    issuing_state: str | None
    issued_date: date | None
    expires_on: date | None
    note: str | None

    model_config = {"from_attributes": True}
