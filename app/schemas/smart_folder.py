from datetime import datetime
from typing import Any

from pydantic import BaseModel


class SmartFolderCreate(BaseModel):
    name: str
    description: str | None = None
    query_json: dict[str, Any]


class SmartFolderUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    query_json: dict[str, Any] | None = None


class SmartFolderResponse(BaseModel):
    id: int
    name: str
    description: str | None = None
    query_json: dict[str, Any] | None = None
    owner_id: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SmartFolderResultsResponse(BaseModel):
    folder: SmartFolderResponse
    document_ids: list[int]
    total: int
