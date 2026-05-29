from datetime import datetime
from typing import Any

from pydantic import BaseModel


class TemplateCreate(BaseModel):
    name: str
    description: str | None = None
    required_fields: dict[str, Any] | None = None
    default_folder_id: int | None = None
    default_lifecycle_type: str | None = None
    extraction_prompt: str | None = None


class TemplateUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    required_fields: dict[str, Any] | None = None
    default_folder_id: int | None = None
    default_lifecycle_type: str | None = None
    extraction_prompt: str | None = None


class TemplateResponse(BaseModel):
    id: int
    name: str
    description: str | None = None
    required_fields: dict[str, Any] | None = None
    default_folder_id: int | None = None
    default_lifecycle_type: str | None = None
    extraction_prompt: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
