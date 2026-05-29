from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.annotation import Annotation
from app.models.document import Document
from app.models.user import User
from app.schemas.annotation import AnnotationCreate, AnnotationResponse

router = APIRouter(tags=["annotations"])


@router.post(
    "/api/documents/{document_id}/annotations",
    response_model=AnnotationResponse,
    status_code=201,
)
async def create_annotation(
    document_id: int,
    data: AnnotationCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    document = await db.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    annotation = Annotation(
        document_id=document_id,
        user_id=current_user.id,
        text=data.text,
        start_offset=data.start_offset,
        end_offset=data.end_offset,
    )
    db.add(annotation)
    await db.flush()
    await db.refresh(annotation)
    return annotation


@router.get(
    "/api/documents/{document_id}/annotations",
    response_model=list[AnnotationResponse],
)
async def list_annotations(
    document_id: int,
    db: AsyncSession = Depends(get_db),
):
    document = await db.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    result = await db.execute(
        select(Annotation)
        .where(Annotation.document_id == document_id)
        .order_by(Annotation.created_at)
    )
    return list(result.scalars().all())
