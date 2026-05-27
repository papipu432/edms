from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user, require_role
from app.models.document import Document
from app.models.lifecycle import DocumentLifecycle, LifecycleTransition
from app.models.user import User
from app.schemas.lifecycle import (
    DocumentLifecycleCreate,
    DocumentLifecycleResponse,
    LifecycleAlertItem,
    LifecycleAlertsResponse,
    LifecycleTransitionRequest,
    LifecycleTransitionResponse,
)
from app.services.email_notifications import EmailNotificationService
from app.services.lifecycle import LifecycleService

router = APIRouter(tags=["lifecycle"])

lifecycle_service = LifecycleService()


@router.post(
    "/api/documents/{document_id}/lifecycle",
    response_model=DocumentLifecycleResponse,
    status_code=201,
)
async def create_lifecycle(
    document_id: int,
    data: DocumentLifecycleCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Check document exists
    document = await db.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    # Check no existing lifecycle
    result = await db.execute(
        select(DocumentLifecycle).where(
            DocumentLifecycle.document_id == document_id
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=400, detail="Lifecycle already exists for this document"
        )

    lifecycle = await lifecycle_service.create_lifecycle(
        db=db,
        document_id=document_id,
        lifecycle_type=data.lifecycle_type,
        expires_at=data.expires_at,
        review_interval_days=data.review_interval_days,
        assigned_reviewer_id=data.assigned_reviewer_id,
    )
    return lifecycle


@router.get(
    "/api/documents/{document_id}/lifecycle",
    response_model=DocumentLifecycleResponse,
)
async def get_lifecycle(
    document_id: int,
    db: AsyncSession = Depends(get_db),
):
    document = await db.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    result = await db.execute(
        select(DocumentLifecycle).where(
            DocumentLifecycle.document_id == document_id
        )
    )
    lifecycle = result.scalar_one_or_none()
    if not lifecycle:
        raise HTTPException(status_code=404, detail="Lifecycle not found")
    return lifecycle


@router.post(
    "/api/documents/{document_id}/lifecycle/transition",
    response_model=DocumentLifecycleResponse,
)
async def transition_lifecycle(
    document_id: int,
    data: LifecycleTransitionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    document = await db.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    result = await db.execute(
        select(DocumentLifecycle).where(
            DocumentLifecycle.document_id == document_id
        )
    )
    lifecycle = result.scalar_one_or_none()
    if not lifecycle:
        raise HTTPException(status_code=404, detail="Lifecycle not found")

    try:
        updated = await lifecycle_service.transition_state(
            db=db,
            lifecycle_id=lifecycle.id,
            target_state=data.target_state,
            user_id=current_user.id,
            comment=data.comment,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return updated


@router.get(
    "/api/documents/{document_id}/lifecycle/history",
    response_model=list[LifecycleTransitionResponse],
)
async def get_lifecycle_history(
    document_id: int,
    db: AsyncSession = Depends(get_db),
):
    document = await db.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    result = await db.execute(
        select(DocumentLifecycle).where(
            DocumentLifecycle.document_id == document_id
        )
    )
    lifecycle = result.scalar_one_or_none()
    if not lifecycle:
        raise HTTPException(status_code=404, detail="Lifecycle not found")

    result = await db.execute(
        select(LifecycleTransition)
        .where(LifecycleTransition.lifecycle_id == lifecycle.id)
        .order_by(LifecycleTransition.created_at)
    )
    return list(result.scalars().all())


@router.get(
    "/api/lifecycle/alerts",
    response_model=LifecycleAlertsResponse,
)
async def get_lifecycle_alerts(
    days_before_expiry: int = 30,
    days_before_review: int = 14,
    db: AsyncSession = Depends(get_db),
):
    alerts_data = await lifecycle_service.get_alerts(
        db, days_before_expiry=days_before_expiry, days_before_review=days_before_review
    )
    alerts = [LifecycleAlertItem(**a) for a in alerts_data]
    return LifecycleAlertsResponse(alerts=alerts, total=len(alerts))


@router.post(
    "/api/lifecycle/check-alerts",
)
async def check_alerts(
    current_user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    email_service = EmailNotificationService()
    count = await email_service.check_and_send_alerts(db)
    return {"alerts_sent": count}
