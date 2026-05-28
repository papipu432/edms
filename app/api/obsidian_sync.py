"""API endpoints for Obsidian sync import."""

from fastapi import APIRouter, Depends, UploadFile

from app.core.config import settings
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.obsidian_sync import SyncResult
from app.services.obsidian_sync import ObsidianSyncService

router = APIRouter(prefix="/api/wiki/sync", tags=["obsidian-sync"])

sync_service = ObsidianSyncService(wiki_path=settings.WIKI_PATH)


@router.post("/import", response_model=SyncResult)
async def import_obsidian_vault(
    file: UploadFile,
    current_user: User = Depends(get_current_user),
) -> SyncResult:
    """Import an Obsidian vault zip file into the wiki.

    Conflict resolution:
    - Obsidian wins for user-created pages (entities/, topics/)
    - EDMS wins for auto-generated summaries (summaries/)
    """
    zip_data = await file.read()
    result = sync_service.import_zip(zip_data)
    return result
