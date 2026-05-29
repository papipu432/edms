from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import require_permission
from app.models.audit import DocumentAuditLog
from app.models.document import Document
from app.models.user import User
from app.schemas.activity import ActivityEntry, ActivityFeedResponse

router = APIRouter(tags=["activity"])


@router.get("/api/activity/feed", response_model=ActivityFeedResponse)
async def get_activity_feed(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(require_permission("audit", "read")),
    db: AsyncSession = Depends(get_db),
):
    count_result = await db.execute(select(func.count(DocumentAuditLog.id)))
    total = count_result.scalar() or 0

    result = await db.execute(
        select(DocumentAuditLog)
        .order_by(DocumentAuditLog.timestamp.desc())
        .offset(offset)
        .limit(limit)
    )
    entries = []
    for log in result.scalars().all():
        entries.append(
            ActivityEntry(
                id=log.id,
                document_id=log.document_id,
                action=log.action,
                actor_username=log.actor_username,
                timestamp=log.timestamp,
                details=log.details_json,
            )
        )

    return ActivityFeedResponse(entries=entries, total=total)


@router.get(
    "/api/documents/{document_id}/activity", response_model=ActivityFeedResponse
)
async def get_document_activity(
    document_id: int,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(require_permission("audit", "read")),
    db: AsyncSession = Depends(get_db),
):
    document = await db.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    count_result = await db.execute(
        select(func.count(DocumentAuditLog.id)).where(
            DocumentAuditLog.document_id == document_id
        )
    )
    total = count_result.scalar() or 0

    result = await db.execute(
        select(DocumentAuditLog)
        .where(DocumentAuditLog.document_id == document_id)
        .order_by(DocumentAuditLog.timestamp.desc())
        .offset(offset)
        .limit(limit)
    )
    entries = []
    for log in result.scalars().all():
        entries.append(
            ActivityEntry(
                id=log.id,
                document_id=log.document_id,
                action=log.action,
                actor_username=log.actor_username,
                timestamp=log.timestamp,
                details=log.details_json,
            )
        )

    return ActivityFeedResponse(entries=entries, total=total)
