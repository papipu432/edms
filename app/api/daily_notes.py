"""API endpoints for daily notes."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.daily_notes import DailyNoteListResponse, DailyNoteResponse
from app.services.daily_notes import DailyNotesService

router = APIRouter(prefix="/api/wiki", tags=["daily-notes"])

daily_notes_service = DailyNotesService(wiki_path=settings.WIKI_PATH)


@router.post("/daily-note", response_model=DailyNoteResponse)
async def generate_daily_note(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DailyNoteResponse:
    """Generate a daily note for today."""
    result = await daily_notes_service.generate_daily_note(db)
    return DailyNoteResponse(**result)


@router.get("/daily-notes", response_model=DailyNoteListResponse)
async def list_daily_notes(
    current_user: User = Depends(get_current_user),
) -> DailyNoteListResponse:
    """List all existing daily notes."""
    notes = daily_notes_service.list_daily_notes()
    return DailyNoteListResponse(notes=notes)
