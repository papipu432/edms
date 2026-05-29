from datetime import datetime

from pydantic import BaseModel


class LockCreate(BaseModel):
    reason: str | None = None
    duration_hours: int = 24


class LockResponse(BaseModel):
    id: int
    document_id: int
    user_id: str
    username: str
    locked_at: datetime
    expires_at: datetime
    reason: str | None = None
    is_expired: bool

    model_config = {"from_attributes": True}


class LockStatusResponse(BaseModel):
    is_locked: bool
    lock: LockResponse | None = None
