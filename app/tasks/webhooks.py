"""Celery task for webhook delivery with retry logic."""

import asyncio

from celery.utils.log import get_task_logger
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.tasks import celery_app

logger = get_task_logger(__name__)


@celery_app.task(
    name="app.tasks.webhooks.deliver_webhook_task",
    max_retries=3,
    default_retry_delay=60,
    autoretry_for=(Exception,),
    retry_backoff=True,
)
def deliver_webhook_task(webhook_id: int, event_type: str, payload: dict) -> None:
    """Deliver a webhook event with automatic retries and exponential backoff."""
    asyncio.run(_deliver_webhook(webhook_id, event_type, payload))


async def _deliver_webhook(webhook_id: int, event_type: str, payload: dict) -> None:
    """Async implementation of webhook delivery."""
    from sqlalchemy import select

    from app.models.webhook import WebhookConfig
    from app.services.webhooks import WebhookService

    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    try:
        async with session_factory() as db:
            result = await db.execute(
                select(WebhookConfig).where(WebhookConfig.id == webhook_id)
            )
            webhook = result.scalar_one_or_none()
            if webhook is None:
                logger.warning("Webhook %d not found, skipping delivery", webhook_id)
                return

            service = WebhookService()
            delivery_result = await service._deliver(webhook, event_type, payload)
            logger.info(
                "Webhook %d delivered for event %s: %s",
                webhook_id,
                event_type,
                delivery_result.get("status", "unknown"),
            )
    finally:
        await engine.dispose()
