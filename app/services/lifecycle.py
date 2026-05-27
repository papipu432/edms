from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.models.lifecycle import (
    DocumentLifecycle,
    DocumentLifecycleState,
    LifecycleTransition,
    LifecycleType,
)


class LifecycleService:
    VALID_TRANSITIONS: dict[DocumentLifecycleState, list[DocumentLifecycleState]] = {
        DocumentLifecycleState.draft: [DocumentLifecycleState.in_review],
        DocumentLifecycleState.in_review: [
            DocumentLifecycleState.approved,
            DocumentLifecycleState.draft,
        ],
        DocumentLifecycleState.approved: [DocumentLifecycleState.up_to_date],
        DocumentLifecycleState.up_to_date: [
            DocumentLifecycleState.needs_re_review,
            DocumentLifecycleState.expired,
        ],
        DocumentLifecycleState.needs_re_review: [
            DocumentLifecycleState.in_review,
            DocumentLifecycleState.expired,
        ],
    }

    async def create_lifecycle(
        self,
        db: AsyncSession,
        document_id: int,
        lifecycle_type: str,
        expires_at: datetime | None = None,
        review_interval_days: int | None = None,
        assigned_reviewer_id: str | None = None,
    ) -> DocumentLifecycle:
        lifecycle = DocumentLifecycle(
            document_id=document_id,
            lifecycle_type=LifecycleType(lifecycle_type),
            state=DocumentLifecycleState.draft,
            expires_at=expires_at,
            review_interval_days=review_interval_days,
            assigned_reviewer_id=assigned_reviewer_id,
        )
        db.add(lifecycle)
        await db.flush()
        await db.refresh(lifecycle)
        return lifecycle

    async def transition_state(
        self,
        db: AsyncSession,
        lifecycle_id: int,
        target_state: str,
        user_id: str,
        comment: str | None = None,
    ) -> DocumentLifecycle:
        lifecycle = await db.get(DocumentLifecycle, lifecycle_id)
        if lifecycle is None:
            raise ValueError("Lifecycle not found")

        current_state = lifecycle.state
        try:
            new_state = DocumentLifecycleState(target_state)
        except ValueError:
            raise ValueError(f"Invalid state: {target_state}")

        valid_targets = self.VALID_TRANSITIONS.get(current_state, [])
        if new_state not in valid_targets:
            raise ValueError(
                f"Invalid transition from '{current_state.value}' to '{new_state.value}'"
            )

        # Create transition record
        transition = LifecycleTransition(
            lifecycle_id=lifecycle_id,
            from_state=current_state,
            to_state=new_state,
            transitioned_by=user_id,
            comment=comment,
        )
        db.add(transition)

        # Update lifecycle state
        lifecycle.state = new_state

        # Handle special logic for certain transitions
        now = datetime.now(timezone.utc)
        if new_state == DocumentLifecycleState.approved:
            lifecycle.last_approved_at = now
            lifecycle.last_reviewed_at = now
        elif new_state == DocumentLifecycleState.up_to_date:
            if (
                lifecycle.lifecycle_type == LifecycleType.recurring
                and lifecycle.review_interval_days
            ):
                lifecycle.next_review_at = now + timedelta(
                    days=lifecycle.review_interval_days
                )

        await db.flush()
        await db.refresh(lifecycle)
        return lifecycle

    async def get_expiring_documents(
        self, db: AsyncSession, days_ahead: int = 30
    ) -> list[DocumentLifecycle]:
        now = datetime.now(timezone.utc)
        cutoff = now + timedelta(days=days_ahead)
        result = await db.execute(
            select(DocumentLifecycle).where(
                DocumentLifecycle.expires_at.isnot(None),
                DocumentLifecycle.expires_at <= cutoff,
                DocumentLifecycle.expires_at > now,
                DocumentLifecycle.state != DocumentLifecycleState.expired,
            )
        )
        return list(result.scalars().all())

    async def get_documents_needing_review(
        self, db: AsyncSession
    ) -> list[DocumentLifecycle]:
        now = datetime.now(timezone.utc)
        result = await db.execute(
            select(DocumentLifecycle).where(
                DocumentLifecycle.next_review_at.isnot(None),
                DocumentLifecycle.next_review_at <= now,
                DocumentLifecycle.state == DocumentLifecycleState.up_to_date,
            )
        )
        return list(result.scalars().all())

    async def get_alerts(
        self,
        db: AsyncSession,
        days_before_expiry: int = 30,
        days_before_review: int = 14,
    ) -> list[dict]:
        now = datetime.now(timezone.utc)
        alerts = []

        # Expiring documents
        expiring = await self.get_expiring_documents(db, days_before_expiry)
        for lc in expiring:
            doc = await db.get(Document, lc.document_id)
            doc_name = doc.original_filename if doc else "Unknown"
            expires_at = lc.expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            days_remaining = (expires_at - now).days
            alerts.append(
                {
                    "document_id": lc.document_id,
                    "document_name": doc_name,
                    "lifecycle_id": lc.id,
                    "alert_type": "expiry",
                    "days_remaining": days_remaining,
                    "expires_at": lc.expires_at,
                    "next_review_at": None,
                }
            )

        # Documents needing review
        review_cutoff = now + timedelta(days=days_before_review)
        result = await db.execute(
            select(DocumentLifecycle).where(
                DocumentLifecycle.next_review_at.isnot(None),
                DocumentLifecycle.next_review_at <= review_cutoff,
                DocumentLifecycle.state == DocumentLifecycleState.up_to_date,
            )
        )
        needing_review = list(result.scalars().all())
        for lc in needing_review:
            doc = await db.get(Document, lc.document_id)
            doc_name = doc.original_filename if doc else "Unknown"
            next_review = lc.next_review_at
            if next_review.tzinfo is None:
                next_review = next_review.replace(tzinfo=timezone.utc)
            days_remaining = (next_review - now).days
            alerts.append(
                {
                    "document_id": lc.document_id,
                    "document_name": doc_name,
                    "lifecycle_id": lc.id,
                    "alert_type": "review",
                    "days_remaining": days_remaining,
                    "expires_at": None,
                    "next_review_at": lc.next_review_at,
                }
            )

        return alerts
