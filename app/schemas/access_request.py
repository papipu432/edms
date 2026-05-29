"""Schemas for access request workflow."""

from datetime import datetime

from pydantic import BaseModel


class AccessRequestCreate(BaseModel):
    resource_type: str
    resource_id: int
    reason: str | None = None


class AccessRequestResponse(BaseModel):
    id: int
    requester_id: str
    resource_type: str
    resource_id: int
    reason: str | None
    status: str
    reviewed_by: str | None
    reviewed_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}
