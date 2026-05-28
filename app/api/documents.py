from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_current_user, get_optional_user
from app.models.document import Document, DocumentStatus
from app.models.group import Group
from app.models.user import User
from app.schemas.document import (
    DocumentListResponse,
    DocumentResponse,
    DocumentStatusResponse,
)
from app.schemas.ocr_quality import OCRQualityResponse
from app.services.audit import AuditService
from app.services.pipeline import PipelineService
from app.services.session_recording import record_access
from app.services.storage import StorageService

router = APIRouter(tags=["documents"])

storage_service = StorageService()
pipeline_service = PipelineService(storage_service=storage_service)
audit_service = AuditService()

# Database URL used by background pipeline task; overridable in tests
pipeline_db_url: str = settings.DATABASE_URL


async def _run_pipeline(doc_id: int, db_url: str, storage_svc: StorageService) -> None:
    """Run the processing pipeline in a background task with its own DB session."""
    engine = create_async_engine(db_url, echo=False)
    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        svc = PipelineService(storage_service=storage_svc)
        await svc.process_document(doc_id, session)
    await engine.dispose()


@router.post(
    "/api/groups/{group_id}/documents",
    response_model=DocumentResponse,
    status_code=201,
)
async def upload_document(
    group_id: int,
    file: UploadFile,
    background_tasks: BackgroundTasks,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_optional_user),
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
        status=DocumentStatus.processing,
    )
    db.add(document)
    await db.flush()
    await db.refresh(document)

    background_tasks.add_task(
        _run_pipeline, document.id, pipeline_db_url, storage_service
    )

    await audit_service.log_action(
        db=db,
        document_id=document.id,
        action="upload",
        actor=current_user,
        request=request,
        details={"filename": filename, "file_size": file_size},
    )

    return document


@router.get("/api/documents", response_model=DocumentListResponse)
async def list_documents(db: AsyncSession = Depends(get_db)) -> dict:
    result = await db.execute(select(Document).order_by(Document.id))
    documents = list(result.scalars().all())
    return {"documents": documents, "total": len(documents)}


@router.get("/api/documents/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: int,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_optional_user),
) -> Document:
    document = await db.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    await audit_service.log_action(
        db=db,
        document_id=document.id,
        action="view",
        actor=current_user,
        request=request,
    )
    if current_user is not None:
        background_tasks.add_task(
            record_access,
            db,
            current_user.id,
            document.id,
            "view",
            request.client.host if request.client else None,
            request.headers.get("user-agent"),
        )
    return document


@router.delete("/api/documents/{document_id}", status_code=204)
async def delete_document(
    document_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_optional_user),
) -> None:
    document = await db.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    await audit_service.log_action(
        db=db,
        document_id=document.id,
        action="delete",
        actor=current_user,
        request=request,
    )

    if document.storage_path:
        storage_service.delete_file(document.storage_path)
    if document.encrypted_pdf_path:
        storage_service.delete_file(document.encrypted_pdf_path)

    await db.delete(document)


@router.get("/api/documents/{document_id}/download")
async def download_document(
    document_id: int,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_optional_user),
) -> FileResponse:
    document = await db.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    await audit_service.log_action(
        db=db,
        document_id=document.id,
        action="download",
        actor=current_user,
        request=request,
    )

    if current_user is not None:
        background_tasks.add_task(
            record_access,
            db,
            current_user.id,
            document.id,
            "download",
            request.client.host if request.client else None,
            request.headers.get("user-agent"),
        )

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


@router.get("/api/documents/{document_id}/status", response_model=DocumentStatusResponse)
async def get_document_status(
    document_id: int, db: AsyncSession = Depends(get_db)
) -> dict:
    document = await db.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"id": document.id, "status": document.status}


@router.get("/api/documents/{document_id}/markdown")
async def get_document_markdown(
    document_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_optional_user),
) -> PlainTextResponse:
    document = await db.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    if document.status != DocumentStatus.processed:
        raise HTTPException(
            status_code=400,
            detail=f"Document is not processed yet. Current status: {document.status.value}",
        )

    if not document.markdown_path or not Path(document.markdown_path).exists():
        raise HTTPException(status_code=404, detail="Markdown file not found")

    await audit_service.log_action(
        db=db,
        document_id=document.id,
        action="view",
        actor=current_user,
        request=request,
        details={"format": "markdown"},
    )

    content = Path(document.markdown_path).read_text(encoding="utf-8")
    return PlainTextResponse(content=content, media_type="text/markdown")


@router.get("/api/documents/{document_id}/ocr-quality", response_model=OCRQualityResponse)
async def get_ocr_quality(
    document_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OCRQualityResponse:
    """Get OCR confidence score and quality info for a document."""
    document = await db.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    confidence = document.ocr_confidence
    needs_review = confidence is not None and confidence < 70.0

    return OCRQualityResponse(
        document_id=document.id,
        ocr_confidence=confidence,
        needs_review=needs_review,
        page_confidences=None,
    )
