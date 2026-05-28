"""Pydantic schemas for daily notes."""

from pydantic import BaseModel


class DailyNoteResponse(BaseModel):
    date: str
    path: str
    content: str


class DailyNoteListResponse(BaseModel):
    notes: list[dict[str, str]]
