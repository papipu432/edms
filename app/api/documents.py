from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.document import Document, DocumentStatus
from app.models.group import Group
from app.schemas.document import DocumentListResponse, DocumentResponse
from app.services.storage import StorageService

router = APIRouter(tags=["documents"])

storage_service = StorageService()


@router.post(
    "/api/groups/{group_id}/documents",
    response_model=DocumentResponse,
    status_code=201,
)
async def upload_document(
    group_id: int,
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
) -> Document:
    group = await db.get(Group, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    filename = file.filename or "unnamed"
    file_content = await file.read()
    file_size = len(file_content)
    await file.seek(0)

    saved_path = await storage_service.save_upload(group_id, file, filename)

    encrypted_path: Path | None = None
    content_type = file.content_type or ""
    if content_type == "application/pdf" or filename.lower().endswith(".pdf"):
        encrypted_path = storage_service.encrypt_pdf(group_id, saved_path, filename)

    document = Document(
        group_id=group_id,
        original_filename=filename,
        storage_path=str(saved_path),
        encrypted_pdf_path=str(encrypted_path) if encrypted_path else None,
        file_type=content_type or "application/octet-stream",
        file_size=file_size,
        status=DocumentStatus.uploaded,
    )
    db.add(document)
    await db.flush()
    await db.refresh(document)
    return document


@router.get("/api/documents", response_model=DocumentListResponse)
async def list_documents(db: AsyncSession = Depends(get_db)) -> dict:
    result = await db.execute(select(Document).order_by(Document.id))
    documents = list(result.scalars().all())
    return {"documents": documents, "total": len(documents)}


@router.get("/api/documents/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: int, db: AsyncSession = Depends(get_db)
) -> Document:
    document = await db.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    return document


@router.delete("/api/documents/{document_id}", status_code=204)
async def delete_document(
    document_id: int, db: AsyncSession = Depends(get_db)
) -> None:
    document = await db.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    if document.storage_path:
        storage_service.delete_file(document.storage_path)
    if document.encrypted_pdf_path:
        storage_service.delete_file(document.encrypted_pdf_path)

    await db.delete(document)


@router.get("/api/documents/{document_id}/download")
async def download_document(
    document_id: int, db: AsyncSession = Depends(get_db)
) -> FileResponse:
    document = await db.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    if document.encrypted_pdf_path and Path(document.encrypted_pdf_path).exists():
        return FileResponse(
            path=document.encrypted_pdf_path,
            filename=document.original_filename,
            media_type="application/pdf",
        )

    if Path(document.storage_path).exists():
        return FileResponse(
            path=document.storage_path,
            filename=document.original_filename,
            media_type=document.file_type,
        )

    raise HTTPException(status_code=404, detail="File not found on disk")
