"""Session recording API router."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.session import SessionListResponse, UserSessionResponse
from app.services.session_recording import SessionRecordingService

router = APIRouter(tags=["sessions"])

session_service = SessionRecordingService()


async def _require_admin(user: User) -> None:
    """Check that the current user has admin role."""
    if "admin" not in user.role_codes:
        raise HTTPException(status_code=403, detail="Admin role required")


@router.get("/api/sessions", response_model=SessionListResponse)
async def list_sessions(
    start_date: str | None = None,
    end_date: str | None = None,
    user_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List sessions (admin only, with optional date and user filters)."""
    await _require_admin(current_user)

    parsed_start = None
    parsed_end = None

    if start_date:
        try:
            parsed_start = datetime.fromisoformat(start_date)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid start_date format")

    if end_date:
        try:
            parsed_end = datetime.fromisoformat(end_date)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid end_date format")

    sessions, total = await session_service.list_sessions(
        db,
        start_date=parsed_start,
        end_date=parsed_end,
        user_id_filter=user_id,
        limit=limit,
        offset=offset,
    )

    return SessionListResponse(sessions=sessions, total=total)


@router.get("/api/sessions/{session_id}", response_model=UserSessionResponse)
async def get_session_detail(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get session detail with documents accessed (admin only)."""
    await _require_admin(current_user)

    session = await session_service.get_session_detail(db, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return session
