"""Import/Export API endpoints."""

from io import BytesIO

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.import_export import ImportResult
from app.services.import_export import ImportExportService

router = APIRouter(tags=["import-export"])

import_export_service = ImportExportService()


@router.post("/api/import", response_model=ImportResult)
async def import_documents(
    file: UploadFile = File(...),
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Import documents from a ZIP file (with manifest.json) or CSV."""
    content = await file.read()
    file_buffer = BytesIO(content)

    if file.filename and file.filename.endswith(".csv"):
        result = await import_export_service.import_csv(db, file_buffer)
    else:
        result = await import_export_service.import_zip(db, file_buffer)

    return ImportResult(**result)


@router.post("/api/export")
async def export_documents(
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Export all documents and metadata as a ZIP archive."""
    buffer = await import_export_service.export_full(db)

    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=edms_export.zip"},
    )
