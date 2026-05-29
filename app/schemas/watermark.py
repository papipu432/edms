from datetime import datetime

from pydantic import BaseModel


class WatermarkConfigCreate(BaseModel):
    group_id: int | None = None
    text_template: str = "{user} - {timestamp} - {doc_id} - CONFIDENTIAL"
    opacity: float = 0.3
    position: str = "diagonal"


class WatermarkConfigUpdate(BaseModel):
    text_template: str | None = None
    opacity: float | None = None
    position: str | None = None
    enabled: bool | None = None


class WatermarkConfigResponse(BaseModel):
    id: int
    group_id: int | None
    text_template: str
    opacity: float
    position: str
    enabled: bool
    created_at: datetime
