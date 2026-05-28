from datetime import datetime

from pydantic import BaseModel


class WebhookCreate(BaseModel):
    url: str
    secret: str
    events: list[str]
    is_active: bool = True
    headers: dict | None = None


class WebhookUpdate(BaseModel):
    url: str | None = None
    secret: str | None = None
    events: list[str] | None = None
    is_active: bool | None = None
    headers: dict | None = None


class WebhookResponse(BaseModel):
    id: int
    url: str
    secret: str
    events: list[str]
    is_active: bool
    headers: dict | None = None
    created_at: datetime
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class WebhookTestResponse(BaseModel):
    webhook_id: int
    status: str
    message: str
