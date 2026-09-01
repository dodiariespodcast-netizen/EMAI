from datetime import datetime

from pydantic import BaseModel


class AuditLogRead(BaseModel):
    id: str
    user_id: str | None
    action: str
    entity_type: str
    entity_id: str | None
    details: dict
    created_at: datetime

    model_config = {"from_attributes": True}
