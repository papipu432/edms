"""Celery task for daily note generation."""

import asyncio

from celery.utils.log import get_task_logger
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.tasks import celery_app

logger = get_task_logger(__name__)


@celery_app.task(name="app.tasks.daily_notes.generate_daily_note_task")
def generate_daily_note_task() -> None:
    """Generate the daily digest note."""
    asyncio.run(_generate_daily_note())


async def _generate_daily_note() -> None:
    """Async implementation of daily note generation."""
    from app.services.daily_notes import DailyNotesService

    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    try:
        async with session_factory() as db:
            service = DailyNotesService()
            result = await service.generate_daily_note(db)
            logger.info("Daily note generated: %s", result.get("path", "unknown"))
    finally:
        await engine.dispose()
