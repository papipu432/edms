from datetime import datetime

from pydantic import BaseModel, Field


class ChatSessionCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    scope_type: str = Field(default="global", pattern="^(global|document|group)$")
    scope_id: int | None = None


class ChatSessionResponse(BaseModel):
    id: str
    title: str
    scope_type: str
    scope_id: int | None
    created_at: datetime
    message_count: int = 0

    model_config = {"from_attributes": True}


class ChatMessageResponse(BaseModel):
    id: str
    role: str
    content: str
    sources: list[dict] | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ChatSendRequest(BaseModel):
    message: str = Field(..., min_length=1)


class ChatSendResponse(BaseModel):
    message: ChatMessageResponse
    session: ChatSessionResponse


class ChatExportResponse(BaseModel):
    format: str
    content: str
