from datetime import datetime
from typing import Any

from pydantic import BaseModel


class ActivityEntry(BaseModel):
    id: str
    document_id: int | None = None
    action: str
    actor_username: str | None = None
    timestamp: datetime
    details: dict[str, Any] | None = None

    model_config = {"from_attributes": True}


class ActivityFeedResponse(BaseModel):
    entries: list[ActivityEntry]
    total: int
