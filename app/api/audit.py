from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import require_permission
from app.models.user import User
from app.schemas.audit import AuditLogListResponse
from app.services.audit import AuditService

router = APIRouter(tags=["audit"])

audit_service = AuditService()


@router.get(
    "/api/documents/{document_id}/history",
    response_model=AuditLogListResponse,
)
async def get_document_history(
    document_id: int,
    action: str | None = Query(None, description="Filter by action type"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(require_permission("audit", "read")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    entries, total = await audit_service.get_document_history(
        db=db,
        document_id=document_id,
        action_filter=action,
        limit=limit,
        offset=offset,
    )
    return {"entries": entries, "total": total}


@router.get(
    "/api/audit/recent",
    response_model=AuditLogListResponse,
)
async def get_recent_activity(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(require_permission("audit", "read")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    entries, total = await audit_service.get_recent_activity(
        db=db,
        limit=limit,
        offset=offset,
    )
    return {"entries": entries, "total": total}
