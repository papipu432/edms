"""Session recording service for tracking user document access."""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.session import SessionDocument, UserSession

logger = logging.getLogger(__name__)

# Session timeout: 30 minutes of inactivity
SESSION_TIMEOUT_MINUTES = 30


class SessionRecordingService:
    """Service for recording user sessions and document access."""

    async def get_or_create_session(
        self,
        db: AsyncSession,
        user_id: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> UserSession:
        """Find an active session or create a new one.

        A session is considered active if:
        - It belongs to the same user and IP
        - It has no ended_at
        - It was started within the last 30 minutes
        """
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=SESSION_TIMEOUT_MINUTES)

        result = await db.execute(
            select(UserSession)
            .where(
                UserSession.user_id == user_id,
                UserSession.ip_address == ip_address,
                UserSession.ended_at.is_(None),
                UserSession.started_at >= cutoff,
            )
            .order_by(UserSession.started_at.desc())
            .limit(1)
        )
        session = result.scalar_one_or_none()

        if session is not None:
            return session

        # Create new session
        session = UserSession(
            user_id=user_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        db.add(session)
        await db.flush()
        await db.refresh(session)
        return session

    async def record_document_access(
        self,
        db: AsyncSession,
        user_id: str,
        document_id: int,
        action: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> SessionDocument:
        """Record a document access within a user session."""
        session = await self.get_or_create_session(db, user_id, ip_address, user_agent)

        doc_access = SessionDocument(
            session_id=session.id,
            document_id=document_id,
            action=action,
        )
        db.add(doc_access)
        await db.flush()
        await db.refresh(doc_access)
        return doc_access

    async def end_session(
        self,
        db: AsyncSession,
        session_id: str,
    ) -> None:
        """End a session by setting ended_at."""
        result = await db.execute(
            select(UserSession).where(UserSession.id == session_id)
        )
        session = result.scalar_one_or_none()
        if session is not None:
            session.ended_at = datetime.now(timezone.utc)
            await db.flush()

    async def list_sessions(
        self,
        db: AsyncSession,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        user_id_filter: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[UserSession], int]:
        """List sessions with optional date range and user filtering."""
        query = select(UserSession)
        count_query = select(func.count(UserSession.id))

        if start_date is not None:
            query = query.where(UserSession.started_at >= start_date)
            count_query = count_query.where(UserSession.started_at >= start_date)
        if end_date is not None:
            query = query.where(UserSession.started_at <= end_date)
            count_query = count_query.where(UserSession.started_at <= end_date)
        if user_id_filter is not None:
            query = query.where(UserSession.user_id == user_id_filter)
            count_query = count_query.where(UserSession.user_id == user_id_filter)

        query = query.order_by(UserSession.started_at.desc()).limit(limit).offset(offset)

        result = await db.execute(query)
        sessions = list(result.scalars().all())

        count_result = await db.execute(count_query)
        total = count_result.scalar() or 0

        return sessions, total

    async def get_session_detail(
        self,
        db: AsyncSession,
        session_id: str,
    ) -> UserSession | None:
        """Get a session with its document access records."""
        result = await db.execute(
            select(UserSession).where(UserSession.id == session_id)
        )
        return result.scalar_one_or_none()


async def record_access(
    db: AsyncSession,
    user_id: str,
    document_id: int,
    action: str,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> None:
    """Fire-and-forget helper to record document access.

    This should not block the main request. Errors are logged and swallowed.
    """
    try:
        service = SessionRecordingService()
        await service.record_document_access(
            db, user_id, document_id, action, ip_address, user_agent
        )
    except Exception:
        logger.warning(
            "Failed to record document access for user=%s doc=%s",
            user_id,
            document_id,
            exc_info=True,
        )
