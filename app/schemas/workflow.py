from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class WorkflowActionRequest(BaseModel):
    comment: str | None = None


class WorkflowEntryResponse(BaseModel):
    id: int
    document_id: int
    user_id: str
    action: str
    comment: str | None = None
    from_stage_id: int | None = None
    to_stage_id: int | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


# Workflow Stage schemas
class WorkflowStageCreate(BaseModel):
    name: str
    code: str
    description: str | None = None
    order_index: int = 0
    color: str | None = None


class WorkflowStageUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    order_index: int | None = None
    color: str | None = None


class WorkflowStageResponse(BaseModel):
    id: int
    name: str
    code: str
    description: str | None = None
    order_index: int
    color: str | None = None
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# Document Workflow schemas (Kanban card)
class DocumentWorkflowMoveRequest(BaseModel):
    to_stage_id: int
    assign_to_user_id: str | None = None
    assign_to_position_id: str | None = None
    comment: str | None = None
    note: str | None = None  # Flow note added during move


class DocumentWorkflowResponse(BaseModel):
    id: int
    document_id: int
    stage_id: int
    assigned_to_user_id: str | None = None
    assigned_to_position_id: str | None = None
    status: str
    priority: str
    due_date: datetime | None = None
    moved_at: datetime
    moved_by_user_id: str | None = None

    model_config = {"from_attributes": True}


# Workflow Note schemas (Flow notes)
class WorkflowNoteCreate(BaseModel):
    content: str
    note_type: str = "comment"  # comment, decision, annotation


class WorkflowNoteResponse(BaseModel):
    id: int
    workflow_id: int
    user_id: str
    note_type: str
    content: str
    created_at: datetime

    model_config = {"from_attributes": True}


# Kanban Board schemas
class KanbanCard(BaseModel):
    id: int
    document_id: int
    title: str
    status: str
    priority: str
    assigned_to_user_id: str | None = None
    assigned_to_position_id: str | None = None
    due_date: str | None = None
    moved_at: str | None = None


class KanbanColumn(BaseModel):
    stage_id: int
    stage_name: str
    stage_code: str
    stage_color: str | None = None
    cards: list[KanbanCard]


class KanbanBoardResponse(BaseModel):
    columns: list[KanbanColumn]
    total_documents: int

