"""Schemas for session recording."""

from datetime import datetime

from pydantic import BaseModel


class SessionDocumentResponse(BaseModel):
    id: int
    session_id: str
    document_id: int
    action: str
    accessed_at: datetime

    model_config = {"from_attributes": True}


class UserSessionResponse(BaseModel):
    id: str
    user_id: str
    started_at: datetime
    ended_at: datetime | None
    ip_address: str | None
    user_agent: str | None
    documents: list[SessionDocumentResponse] = []

    model_config = {"from_attributes": True}


class SessionListResponse(BaseModel):
    sessions: list[UserSessionResponse]
    total: int
