from datetime import datetime

from pydantic import BaseModel


class AuditLogEntry(BaseModel):
    id: str
    document_id: int
    action: str
    actor_id: str | None = None
    actor_username: str | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    timestamp: datetime
    details_json: dict | None = None

    model_config = {"from_attributes": True}


class AuditLogListResponse(BaseModel):
    entries: list[AuditLogEntry]
    total: int
