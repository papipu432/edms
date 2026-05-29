from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.document import Document
from app.models.lifecycle import DocumentLifecycle
from app.models.user import User
from app.schemas.kanban import KanbanBoard, KanbanCard

router = APIRouter(tags=["kanban"])


@router.get("/api/kanban", response_model=KanbanBoard)
async def get_kanban_board(
    limit: int = Query(100, ge=1, le=500),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(DocumentLifecycle, Document)
        .join(Document, Document.id == DocumentLifecycle.document_id)
        .order_by(DocumentLifecycle.updated_at.desc())
        .limit(limit)
    )

    columns: dict[str, list[KanbanCard]] = {}
    for lifecycle, document in result.all():
        state = lifecycle.state.value if hasattr(lifecycle.state, "value") else str(lifecycle.state)
        card = KanbanCard(
            document_id=document.id,
            filename=document.original_filename,
            state=state,
            updated_at=lifecycle.updated_at,
            assigned_reviewer=lifecycle.assigned_reviewer_id,
        )
        if state not in columns:
            columns[state] = []
        columns[state].append(card)

    return KanbanBoard(columns=columns)
