"""Offline package generation API endpoints."""

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.offline import OfflineRequest
from app.services.offline_package import OfflinePackageService

router = APIRouter(tags=["offline"])

offline_service = OfflinePackageService()


@router.post("/api/offline/generate")
async def generate_offline_package(
    data: OfflineRequest,
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate an offline package ZIP with self-contained HTML viewer."""
    buffer = await offline_service.generate_package(
        db, document_ids=data.document_ids, group_id=data.group_id
    )

    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=offline_package.zip"},
    )
