"""Access request workflow service."""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.access_request import AccessRequest
from app.models.audit import DocumentAuditLog
from app.services.notifications import get_notification_manager


class AccessRequestService:
    """Service for managing access request workflow."""

    async def create_request(
        self,
        db: AsyncSession,
        requester_id: str,
        resource_type: str,
        resource_id: int,
        reason: str | None = None,
    ) -> AccessRequest:
        """Create a new access request and notify admins."""
        access_request = AccessRequest(
            requester_id=requester_id,
            resource_type=resource_type,
            resource_id=resource_id,
            reason=reason,
            status="pending",
        )
        db.add(access_request)
        await db.flush()
        await db.refresh(access_request)

        # Notify admins about the new request
        notification_manager = get_notification_manager()
        await notification_manager.create_notification(
            db=db,
            user_id=None,  # broadcast to all (admins)
            notification_type="access_request",
            title="New Access Request",
            message=(
                f"User requested access to {resource_type} #{resource_id}"
                + (f": {reason}" if reason else "")
            ),
            data={
                "request_id": access_request.id,
                "requester_id": requester_id,
                "resource_type": resource_type,
                "resource_id": resource_id,
            },
        )

        return access_request

    async def list_pending(
        self,
        db: AsyncSession,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AccessRequest]:
        """List all pending access requests (for admins)."""
        result = await db.execute(
            select(AccessRequest)
            .where(AccessRequest.status == "pending")
            .order_by(AccessRequest.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def list_user_requests(
        self,
        db: AsyncSession,
        user_id: str,
    ) -> list[AccessRequest]:
        """List access requests for a specific user."""
        result = await db.execute(
            select(AccessRequest)
            .where(AccessRequest.requester_id == user_id)
            .order_by(AccessRequest.created_at.desc())
        )
        return list(result.scalars().all())

    async def approve_request(
        self,
        db: AsyncSession,
        request_id: int,
        reviewer_id: str,
    ) -> AccessRequest | None:
        """Approve an access request and log the access grant.

        Note: Full ACL integration would require a GroupMembership model.
        Currently, approval is recorded in the audit log as evidence of the grant.
        """
        result = await db.execute(
            select(AccessRequest).where(AccessRequest.id == request_id)
        )
        access_request = result.scalar_one_or_none()
        if access_request is None:
            return None

        access_request.status = "approved"
        access_request.reviewed_by = reviewer_id
        access_request.reviewed_at = datetime.now(timezone.utc)

        # Log the access grant in the audit trail so there is a record of
        # the permission being conferred. For resource_type="document", the
        # document_id is the resource; for "group" we record with document_id
        # set to None and capture details in the JSON payload.
        doc_id = (
            access_request.resource_id
            if access_request.resource_type == "document"
            else None
        )
        audit_entry = DocumentAuditLog(
            document_id=doc_id,
            action="access_granted",
            actor_id=reviewer_id,
            actor_username=None,
            details_json={
                "request_id": access_request.id,
                "requester_id": access_request.requester_id,
                "resource_type": access_request.resource_type,
                "resource_id": access_request.resource_id,
                "reason": access_request.reason,
            },
        )
        db.add(audit_entry)

        await db.flush()
        await db.refresh(access_request)
        return access_request

    async def deny_request(
        self,
        db: AsyncSession,
        request_id: int,
        reviewer_id: str,
    ) -> AccessRequest | None:
        """Deny an access request."""
        result = await db.execute(
            select(AccessRequest).where(AccessRequest.id == request_id)
        )
        access_request = result.scalar_one_or_none()
        if access_request is None:
            return None

        access_request.status = "denied"
        access_request.reviewed_by = reviewer_id
        access_request.reviewed_at = datetime.now(timezone.utc)
        await db.flush()
        await db.refresh(access_request)
        return access_request
