from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.document import Document
from app.schemas.relationship import (
    OrphanedDocumentResponse,
    RelationshipCreate,
    RelationshipGraphResponse,
    RelationshipResponse,
)
from app.services.relationships import RelationshipService

router = APIRouter(tags=["relationships"])

relationship_service = RelationshipService()


@router.post(
    "/api/documents/{document_id}/relationships",
    response_model=RelationshipResponse,
    status_code=201,
)
async def create_relationship(
    document_id: int,
    payload: RelationshipCreate,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Create a relationship from this document to another document."""
    try:
        rel = await relationship_service.add_relationship(
            db=db,
            source_document_id=document_id,
            target_document_id=payload.target_document_id,
            relationship_type=payload.relationship_type,
            description=payload.description,
        )
    except ValueError as e:
        error_msg = str(e)
        if "not found" in error_msg:
            raise HTTPException(status_code=404, detail=error_msg)
        raise HTTPException(status_code=400, detail=error_msg)
    return rel


@router.get(
    "/api/documents/{document_id}/relationships",
    response_model=list[RelationshipResponse],
)
async def list_document_relationships(
    document_id: int,
    db: AsyncSession = Depends(get_db),
) -> list:
    """Get all relationships for a document (as source or target)."""
    document = await db.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    return await relationship_service.get_document_relationships(db, document_id)


@router.delete("/api/relationships/{relationship_id}", status_code=204)
async def delete_relationship(
    relationship_id: int,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Remove a relationship by ID."""
    deleted = await relationship_service.remove_relationship(db, relationship_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Relationship not found")


@router.get("/api/relationships/graph", response_model=RelationshipGraphResponse)
async def get_relationship_graph(
    group_id: int | None = Query(None, description="Filter by group ID"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get the full relationship graph or filtered by group."""
    return await relationship_service.get_relationship_graph(db, group_id=group_id)


@router.get(
    "/api/relationships/orphaned",
    response_model=list[OrphanedDocumentResponse],
)
async def get_orphaned_documents(
    db: AsyncSession = Depends(get_db),
) -> list:
    """Detect documents with broken relationships (referencing deleted documents)."""
    return await relationship_service.detect_orphaned_documents(db)


@router.get(
    "/api/documents/{document_id}/dependencies",
    response_model=list[int],
)
async def get_document_dependencies(
    document_id: int,
    db: AsyncSession = Depends(get_db),
) -> list[int]:
    """Get transitive dependencies for a document."""
    document = await db.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    return await relationship_service.get_document_dependencies(db, document_id)
