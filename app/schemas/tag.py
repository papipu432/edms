from datetime import datetime

from pydantic import BaseModel


class TagCreate(BaseModel):
    name: str
    color: str | None = None


class TagResponse(BaseModel):
    id: int
    name: str
    color: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class DocumentTagResponse(BaseModel):
    id: int
    document_id: int
    tag_id: int
    created_at: datetime

    model_config = {"from_attributes": True}
