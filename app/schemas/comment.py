from datetime import datetime

from pydantic import BaseModel


class CommentCreate(BaseModel):
    content: str
    parent_id: int | None = None


class CommentUpdate(BaseModel):
    content: str


class CommentResponse(BaseModel):
    id: int
    document_id: int
    user_id: str
    username: str
    content: str
    parent_id: int | None = None
    created_at: datetime
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}
