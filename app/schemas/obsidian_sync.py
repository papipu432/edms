"""Pydantic schemas for Obsidian sync import."""

from pydantic import BaseModel


class SyncConflict(BaseModel):
    path: str
    resolution: str
    detail: str


class SyncResult(BaseModel):
    pages_created: int
    pages_updated: int
    pages_deleted: int
    conflicts: list[SyncConflict]


class SyncManifest(BaseModel):
    last_sync: str
    file_hashes: dict[str, str]
