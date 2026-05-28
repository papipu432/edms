"""Celery task for backup operations."""

import asyncio
from datetime import datetime, timezone

from celery.utils.log import get_task_logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.tasks import celery_app

logger = get_task_logger(__name__)


@celery_app.task(name="app.tasks.backup.trigger_backup_task")
def trigger_backup_task(job_id: int, target: str) -> None:
    """Run a backup and update the job record."""
    asyncio.run(_run_backup(job_id, target))


async def _run_backup(job_id: int, target: str) -> None:
    """Async implementation of backup execution."""
    from app.models.backup import BackupJob
    from app.services.backup import BackupService

    backup_service = BackupService()
    result = await backup_service.run_backup(target=target)

    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    try:
        async with session_factory() as db:
            stmt = select(BackupJob).where(BackupJob.id == job_id)
            res = await db.execute(stmt)
            job = res.scalar_one_or_none()
            if job:
                job.status = result.get("status", "failed")
                job.finished_at = datetime.now(timezone.utc)
                if result.get("detail"):
                    job.error_message = result["detail"]
                await db.commit()
    except Exception as e:
        logger.error("Failed to update backup job %s: %s", job_id, e)
    finally:
        await engine.dispose()

    logger.info("Backup task completed for job %s, target: %s", job_id, target)
