from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.document import Document
from app.models.tag import DocumentTag, Tag
from app.models.user import User
from app.schemas.tag import TagCreate, TagResponse

router = APIRouter(tags=["tags"])


@router.post("/api/tags", response_model=TagResponse, status_code=201)
async def create_tag(
    data: TagCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tag = Tag(name=data.name, color=data.color)
    db.add(tag)
    await db.commit()
    await db.refresh(tag)
    return tag


@router.get("/api/tags", response_model=list[TagResponse])
async def list_tags(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Tag).order_by(Tag.name))
    return list(result.scalars().all())


@router.delete("/api/tags/{tag_id}", status_code=204)
async def delete_tag(
    tag_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tag = await db.get(Tag, tag_id)
    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found")
    await db.delete(tag)
    await db.commit()


@router.post(
    "/api/documents/{document_id}/tags", response_model=TagResponse, status_code=201
)
async def add_tag_to_document(
    document_id: int,
    data: TagCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    document = await db.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    # Find or create tag
    result = await db.execute(select(Tag).where(Tag.name == data.name))
    tag = result.scalar_one_or_none()
    if not tag:
        tag = Tag(name=data.name, color=data.color)
        db.add(tag)
        await db.flush()

    # Check if already linked
    result = await db.execute(
        select(DocumentTag).where(
            DocumentTag.document_id == document_id, DocumentTag.tag_id == tag.id
        )
    )
    if result.scalar_one_or_none():
        return tag

    doc_tag = DocumentTag(document_id=document_id, tag_id=tag.id)
    db.add(doc_tag)
    await db.commit()
    await db.refresh(tag)
    return tag


@router.delete("/api/documents/{document_id}/tags/{tag_id}", status_code=204)
async def remove_tag_from_document(
    document_id: int,
    tag_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(DocumentTag).where(
            DocumentTag.document_id == document_id, DocumentTag.tag_id == tag_id
        )
    )
    doc_tag = result.scalar_one_or_none()
    if not doc_tag:
        raise HTTPException(status_code=404, detail="Tag not found on document")
    await db.delete(doc_tag)
    await db.commit()


@router.get("/api/documents/{document_id}/tags", response_model=list[TagResponse])
async def get_document_tags(
    document_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    document = await db.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    result = await db.execute(
        select(Tag)
        .join(DocumentTag, DocumentTag.tag_id == Tag.id)
        .where(DocumentTag.document_id == document_id)
    )
    return list(result.scalars().all())
