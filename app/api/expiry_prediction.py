from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.document import Document
from app.models.lifecycle import DocumentLifecycle
from app.models.user import User
from app.schemas.expiry_prediction import ExpiryPrediction

router = APIRouter(tags=["expiry_prediction"])


@router.get(
    "/api/documents/{document_id}/expiry-prediction",
    response_model=ExpiryPrediction,
)
async def predict_document_expiry(
    document_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    document = await db.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    # Get lifecycle for this document
    result = await db.execute(
        select(DocumentLifecycle).where(
            DocumentLifecycle.document_id == document_id
        )
    )
    lifecycle = result.scalar_one_or_none()
    if not lifecycle:
        raise HTTPException(status_code=404, detail="No lifecycle found for document")

    # Find documents in same folder to calculate average lifecycle duration
    result = await db.execute(
        select(DocumentLifecycle).join(
            Document, Document.id == DocumentLifecycle.document_id
        ).where(Document.group_id == document.group_id)
    )
    sibling_lifecycles = result.scalars().all()

    # Calculate average review interval from transitions
    total_days = 0
    count = 0
    for sibling in sibling_lifecycles:
        if sibling.review_interval_days:
            total_days += sibling.review_interval_days
            count += 1

    if count == 0:
        # No data to predict from
        return ExpiryPrediction(
            document_id=document_id,
            predicted_review_date=lifecycle.next_review_at or lifecycle.expires_at,
            confidence=0.0,
            based_on_count=0,
        )

    avg_days = total_days / count
    # Predict from last review or creation
    base_date = lifecycle.last_reviewed_at or lifecycle.created_at
    predicted_date = base_date + timedelta(days=avg_days)

    # Confidence based on sample size (max out at 1.0 with 10+ samples)
    confidence = min(count / 10.0, 1.0)

    return ExpiryPrediction(
        document_id=document_id,
        predicted_review_date=predicted_date,
        confidence=round(confidence, 2),
        based_on_count=count,
    )
