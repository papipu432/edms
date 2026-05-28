from datetime import datetime

from pydantic import BaseModel


class TenantCreate(BaseModel):
    name: str
    slug: str
    settings: dict | None = None
    is_active: bool = True


class TenantUpdate(BaseModel):
    name: str | None = None
    slug: str | None = None
    settings: dict | None = None
    is_active: bool | None = None


class TenantResponse(BaseModel):
    id: int
    name: str
    slug: str
    settings: dict | None = None
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}
