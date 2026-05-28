"""Pydantic schemas for Canvas/Whiteboard."""

from datetime import datetime

from pydantic import BaseModel


# Canvas schemas
class CanvasCreate(BaseModel):
    name: str


class CanvasUpdate(BaseModel):
    name: str | None = None


class CanvasResponse(BaseModel):
    id: int
    name: str
    owner_id: str
    created_at: datetime

    model_config = {"from_attributes": True}


# CanvasItem schemas
class CanvasItemCreate(BaseModel):
    document_id: int | None = None
    note_text: str | None = None
    x_position: float = 0.0
    y_position: float = 0.0
    width: float = 200.0
    height: float = 100.0
    color: str | None = None


class CanvasItemUpdate(BaseModel):
    document_id: int | None = None
    note_text: str | None = None
    x_position: float | None = None
    y_position: float | None = None
    width: float | None = None
    height: float | None = None
    color: str | None = None


class CanvasItemResponse(BaseModel):
    id: int
    canvas_id: int
    document_id: int | None = None
    note_text: str | None = None
    x_position: float
    y_position: float
    width: float
    height: float
    color: str | None = None

    model_config = {"from_attributes": True}


# CanvasConnection schemas
class CanvasConnectionCreate(BaseModel):
    from_item_id: int
    to_item_id: int
    label: str | None = None


class CanvasConnectionUpdate(BaseModel):
    label: str | None = None


class CanvasConnectionResponse(BaseModel):
    id: int
    canvas_id: int
    from_item_id: int
    to_item_id: int
    label: str | None = None

    model_config = {"from_attributes": True}


# Export schema (Obsidian .canvas format)
class CanvasExportNode(BaseModel):
    id: str
    x: float
    y: float
    width: float
    height: float
    type: str
    text: str | None = None
    color: str | None = None


class CanvasExportEdge(BaseModel):
    id: str
    fromNode: str
    toNode: str
    label: str | None = None


class CanvasExport(BaseModel):
    nodes: list[CanvasExportNode]
    edges: list[CanvasExportEdge]
