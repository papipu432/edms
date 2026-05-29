import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.document import Document
from app.models.user import User
from app.schemas.preview import PreviewMetadata
from app.services.preview import PreviewService

router = APIRouter(tags=["preview"])

preview_service = PreviewService()


@router.get("/api/documents/{document_id}/preview")
async def get_document_preview(
    document_id: int,
    type: str | None = Query(None, description="Force preview type: thumbnail or html"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Return the cached preview for a document."""
    document = await db.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    png_path = preview_service.get_preview_path(document_id)
    html_path = preview_service.get_html_preview_path(document_id)

    # If type is specified, only check that type
    if type == "thumbnail":
        if png_path.exists():
            return Response(content=png_path.read_bytes(), media_type="image/png")
    elif type == "html":
        if html_path.exists():
            return HTMLResponse(content=html_path.read_text(encoding="utf-8"))

    # Default: check both (PNG first, then HTML)
    if type is None or type == "thumbnail":
        if png_path.exists():
            return Response(content=png_path.read_bytes(), media_type="image/png")
    if type is None or type == "html":
        if html_path.exists():
            return HTMLResponse(content=html_path.read_text(encoding="utf-8"))

    # Attempt on-the-fly generation
    file_path = Path(document.storage_path) if document.storage_path else None
    markdown_content: str | None = None
    if document.markdown_path and Path(document.markdown_path).exists():
        markdown_content = Path(document.markdown_path).read_text(encoding="utf-8")

    if file_path and file_path.exists():
        result = preview_service.generate_and_cache(
            document_id=document_id,
            file_path=file_path,
            file_type=document.file_type,
            markdown_content=markdown_content,
        )
        if result:
            if result.endswith(".html"):
                return HTMLResponse(content=Path(result).read_text(encoding="utf-8"))
            return Response(content=Path(result).read_bytes(), media_type="image/png")
    elif markdown_content:
        result = preview_service.generate_and_cache(
            document_id=document_id,
            file_path=Path(""),
            file_type=document.file_type,
            markdown_content=markdown_content,
        )
        if result:
            return HTMLResponse(content=Path(result).read_text(encoding="utf-8"))

    raise HTTPException(status_code=404, detail="No preview available")


@router.get(
    "/api/documents/{document_id}/preview/metadata",
    response_model=PreviewMetadata,
)
async def get_preview_metadata(
    document_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return metadata about the preview for a document."""
    document = await db.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    png_path = preview_service.get_preview_path(document_id)
    html_path = preview_service.get_html_preview_path(document_id)

    if png_path.exists():
        return {
            "document_id": document_id,
            "preview_type": "png",
            "file_size": os.path.getsize(png_path),
            "exists": True,
        }
    elif html_path.exists():
        return {
            "document_id": document_id,
            "preview_type": "html",
            "file_size": os.path.getsize(html_path),
            "exists": True,
        }

    return {
        "document_id": document_id,
        "preview_type": "",
        "file_size": 0,
        "exists": False,
    }
