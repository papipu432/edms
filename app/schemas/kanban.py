from datetime import datetime

from pydantic import BaseModel


class KanbanCard(BaseModel):
    document_id: int
    filename: str
    state: str
    updated_at: datetime
    assigned_reviewer: str | None = None


class KanbanBoard(BaseModel):
    columns: dict[str, list[KanbanCard]]
