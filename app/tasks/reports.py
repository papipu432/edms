"""Celery task for scheduled report generation."""

import asyncio

from celery.utils.log import get_task_logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.tasks import celery_app

logger = get_task_logger(__name__)


@celery_app.task(name="app.tasks.reports.generate_scheduled_reports_task")
def generate_scheduled_reports_task() -> None:
    """Generate all pending scheduled reports."""
    asyncio.run(_generate_reports())


async def _generate_reports() -> None:
    """Async implementation of report generation."""
    from app.models.scheduled_report import ScheduledReport
    from app.services.scheduled_reports import ScheduledReportService

    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    try:
        async with session_factory() as db:
            result = await db.execute(
                select(ScheduledReport).where(ScheduledReport.is_active.is_(True))
            )
            reports = result.scalars().all()

            service = ScheduledReportService()
            for report in reports:
                try:
                    await service.trigger_report(db, report.id)
                    logger.info("Generated report: %s (id=%d)", report.name, report.id)
                except Exception as e:
                    logger.error(
                        "Failed to generate report %s (id=%d): %s",
                        report.name,
                        report.id,
                        e,
                    )
    finally:
        await engine.dispose()

    logger.info("Scheduled reports task completed")
