"""Celery task for lifecycle alert checks."""

import asyncio
from datetime import datetime, timedelta, timezone

from celery.utils.log import get_task_logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.tasks import celery_app

logger = get_task_logger(__name__)


@celery_app.task(name="app.tasks.lifecycle.check_lifecycle_alerts_task")
def check_lifecycle_alerts_task() -> None:
    """Check for documents with upcoming expiry/review dates and send alerts."""
    asyncio.run(_check_lifecycle_alerts())


async def _check_lifecycle_alerts() -> None:
    """Async implementation of lifecycle alert checking."""
    from app.models.document import Document
    from app.models.lifecycle import DocumentLifecycle, DocumentLifecycleState
    from app.services.email_notifications import EmailNotificationService

    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    try:
        async with session_factory() as db:
            now = datetime.now(timezone.utc)
            expiry_threshold = now + timedelta(days=settings.ALERT_DAYS_BEFORE_EXPIRY)
            review_threshold = now + timedelta(days=settings.ALERT_DAYS_BEFORE_REVIEW)

            # Find documents expiring soon
            expiring_result = await db.execute(
                select(DocumentLifecycle).where(
                    DocumentLifecycle.expires_at.isnot(None),
                    DocumentLifecycle.expires_at <= expiry_threshold,
                    DocumentLifecycle.expires_at > now,
                    DocumentLifecycle.state != DocumentLifecycleState.expired,
                )
            )
            expiring = expiring_result.scalars().all()

            email_service = EmailNotificationService()

            for lifecycle in expiring:
                doc = await db.get(Document, lifecycle.document_id)
                if doc:
                    days_remaining = (lifecycle.expires_at - now).days
                    email_service.send_lifecycle_alert(
                        to_email=settings.SMTP_FROM_EMAIL,
                        document_name=doc.original_filename,
                        alert_type="expiry",
                        days_remaining=days_remaining,
                    )

            # Find documents due for review
            review_result = await db.execute(
                select(DocumentLifecycle).where(
                    DocumentLifecycle.next_review_at.isnot(None),
                    DocumentLifecycle.next_review_at <= review_threshold,
                    DocumentLifecycle.next_review_at > now,
                    DocumentLifecycle.state == DocumentLifecycleState.up_to_date,
                )
            )
            review_due = review_result.scalars().all()

            for lifecycle in review_due:
                doc = await db.get(Document, lifecycle.document_id)
                if doc:
                    days_remaining = (lifecycle.next_review_at - now).days
                    email_service.send_lifecycle_alert(
                        to_email=settings.SMTP_FROM_EMAIL,
                        document_name=doc.original_filename,
                        alert_type="review",
                        days_remaining=days_remaining,
                    )

            logger.info(
                "Lifecycle check complete: %d expiring, %d due for review",
                len(expiring),
                len(review_due),
            )
    finally:
        await engine.dispose()
