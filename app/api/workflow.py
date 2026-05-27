from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.document import Document
from app.models.user import User
from app.models.workflow import WorkflowAction, WorkflowEntry
from app.schemas.workflow import WorkflowActionRequest, WorkflowEntryResponse

router = APIRouter(tags=["workflow"])


@router.post(
    "/api/documents/{document_id}/workflow/{action}",
    response_model=WorkflowEntryResponse,
    status_code=201,
)
async def create_workflow_action(
    document_id: int,
    action: WorkflowAction,
    data: WorkflowActionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    document = await db.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    entry = WorkflowEntry(
        document_id=document_id,
        user_id=current_user.id,
        action=action,
        comment=data.comment,
    )
    db.add(entry)
    await db.flush()
    await db.refresh(entry)
    return entry


@router.get(
    "/api/documents/{document_id}/workflow",
    response_model=list[WorkflowEntryResponse],
)
async def get_workflow_history(
    document_id: int,
    db: AsyncSession = Depends(get_db),
):
    document = await db.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    result = await db.execute(
        select(WorkflowEntry)
        .where(WorkflowEntry.document_id == document_id)
        .order_by(WorkflowEntry.created_at)
    )
    return list(result.scalars().all())
