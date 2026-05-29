from datetime import datetime

from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import DocumentAuditLog
from app.models.user import User


class AuditService:
    """Append-only audit trail service for document operations."""

    async def log_action(
        self,
        db: AsyncSession,
        document_id: int,
        action: str,
        actor: User | None = None,
        request: Request | None = None,
        details: dict | None = None,
    ) -> DocumentAuditLog:
        """Create an audit log entry for a document action."""
        ip_address: str | None = None
        user_agent_str: str | None = None

        if request is not None:
            if request.client:
                ip_address = request.client.host
            user_agent_str = request.headers.get("user-agent")

        actor_id: str | None = None
        actor_username: str | None = "system"

        if actor is not None:
            actor_id = actor.id
            actor_username = actor.username

        entry = DocumentAuditLog(
            document_id=document_id,
            action=action,
            actor_id=actor_id,
            actor_username=actor_username,
            ip_address=ip_address,
            user_agent=user_agent_str,
            details_json=details,
        )
        db.add(entry)
        await db.flush()
        return entry

    async def get_document_history(
        self,
        db: AsyncSession,
        document_id: int,
        action_filter: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[DocumentAuditLog], int]:
        """Query audit log for a specific document with optional filters."""
        query = select(DocumentAuditLog).where(
            DocumentAuditLog.document_id == document_id
        )
        count_query = select(func.count()).select_from(DocumentAuditLog).where(
            DocumentAuditLog.document_id == document_id
        )

        if action_filter:
            query = query.where(DocumentAuditLog.action == action_filter)
            count_query = count_query.where(DocumentAuditLog.action == action_filter)

        if start_date:
            query = query.where(DocumentAuditLog.timestamp >= start_date)
            count_query = count_query.where(DocumentAuditLog.timestamp >= start_date)

        if end_date:
            query = query.where(DocumentAuditLog.timestamp <= end_date)
            count_query = count_query.where(DocumentAuditLog.timestamp <= end_date)

        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        query = query.order_by(DocumentAuditLog.timestamp.desc())
        query = query.limit(limit).offset(offset)

        result = await db.execute(query)
        entries = list(result.scalars().all())

        return entries, total

    async def get_recent_activity(
        self,
        db: AsyncSession,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[DocumentAuditLog], int]:
        """Get recent audit entries across all documents."""
        count_query = select(func.count()).select_from(DocumentAuditLog)
        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        query = (
            select(DocumentAuditLog)
            .order_by(DocumentAuditLog.timestamp.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await db.execute(query)
        entries = list(result.scalars().all())

        return entries, total
