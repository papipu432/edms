from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security import require_permission
from app.models.backup import BackupJob, BackupSchedule
from app.models.user import User
from app.services.backup import BackupService

router = APIRouter(tags=["settings-backup"])
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))
backup_service = BackupService()


class BackupConfigUpdate(BaseModel):
    minio_primary_endpoint: str | None = None
    minio_primary_access_key: str | None = None
    minio_primary_secret_key: str | None = None
    minio_primary_bucket: str | None = None
    minio_dr_endpoint: str | None = None
    minio_dr_access_key: str | None = None
    minio_dr_secret_key: str | None = None
    minio_dr_bucket: str | None = None
    restic_repository: str | None = None
    restic_password: str | None = None
    backup_retention_days: int | None = None


class ScheduleUpdate(BaseModel):
    cron_expression: str
    is_active: bool = True


@router.get("/settings/backup")
async def settings_backup_page(
    request: Request,
    _user: User = Depends(require_permission("settings", "manage")),
):
    """Render the Backup settings HTML page."""
    return templates.TemplateResponse(request, "settings_backup.html")


@router.get("/api/settings/backup/config")
async def get_backup_config(
    _user: User = Depends(require_permission("settings", "manage")),
):
    """Return current backup configuration as JSON."""
    return {
        "minio_primary_endpoint": settings.MINIO_PRIMARY_ENDPOINT,
        "minio_primary_access_key": settings.MINIO_PRIMARY_ACCESS_KEY,
        "minio_primary_secret_key": "***" if settings.MINIO_PRIMARY_SECRET_KEY else "",
        "minio_primary_bucket": settings.MINIO_PRIMARY_BUCKET,
        "minio_dr_endpoint": settings.MINIO_DR_ENDPOINT,
        "minio_dr_access_key": settings.MINIO_DR_ACCESS_KEY,
        "minio_dr_secret_key": "***" if settings.MINIO_DR_SECRET_KEY else "",
        "minio_dr_bucket": settings.MINIO_DR_BUCKET,
        "restic_repository": settings.RESTIC_REPOSITORY,
        "restic_password": "***" if settings.RESTIC_PASSWORD else "",
        "backup_schedule": settings.BACKUP_SCHEDULE,
        "backup_retention_days": settings.BACKUP_RETENTION_DAYS,
    }


@router.post("/api/settings/backup/config")
async def update_backup_config(
    config: BackupConfigUpdate,
    _user: User = Depends(require_permission("settings", "manage")),
):
    """Update backup configuration (runtime only)."""
    if config.minio_primary_endpoint is not None:
        settings.MINIO_PRIMARY_ENDPOINT = config.minio_primary_endpoint
    if config.minio_primary_access_key is not None:
        settings.MINIO_PRIMARY_ACCESS_KEY = config.minio_primary_access_key
    if config.minio_primary_secret_key is not None:
        settings.MINIO_PRIMARY_SECRET_KEY = config.minio_primary_secret_key
    if config.minio_primary_bucket is not None:
        settings.MINIO_PRIMARY_BUCKET = config.minio_primary_bucket
    if config.minio_dr_endpoint is not None:
        settings.MINIO_DR_ENDPOINT = config.minio_dr_endpoint
    if config.minio_dr_access_key is not None:
        settings.MINIO_DR_ACCESS_KEY = config.minio_dr_access_key
    if config.minio_dr_secret_key is not None:
        settings.MINIO_DR_SECRET_KEY = config.minio_dr_secret_key
    if config.minio_dr_bucket is not None:
        settings.MINIO_DR_BUCKET = config.minio_dr_bucket
    if config.restic_repository is not None:
        settings.RESTIC_REPOSITORY = config.restic_repository
    if config.restic_password is not None:
        settings.RESTIC_PASSWORD = config.restic_password
    if config.backup_retention_days is not None:
        settings.BACKUP_RETENTION_DAYS = config.backup_retention_days
    return {"status": "ok"}


@router.get("/api/settings/backup/history")
async def get_backup_history(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_permission("settings", "manage")),
):
    """List backup jobs from the database."""
    result = await db.execute(
        select(BackupJob).order_by(BackupJob.created_at.desc()).limit(50)
    )
    jobs = result.scalars().all()
    return {
        "jobs": [
            {
                "id": job.id,
                "job_type": job.job_type,
                "status": job.status,
                "started_at": job.started_at.isoformat() if job.started_at else None,
                "finished_at": job.finished_at.isoformat() if job.finished_at else None,
                "size_bytes": job.size_bytes,
                "files_count": job.files_count,
                "target": job.target,
                "error_message": job.error_message,
                "created_at": job.created_at.isoformat() if job.created_at else None,
            }
            for job in jobs
        ]
    }


async def _run_backup_task(job_id: str, target: str) -> None:
    """Background task to run a backup."""
    result = await backup_service.run_backup(target=target)

    try:
        from app.core.database import get_db_session

        async with get_db_session() as db:
            stmt = select(BackupJob).where(BackupJob.id == job_id)
            res = await db.execute(stmt)
            job = res.scalar_one_or_none()
            if job:
                job.status = result.get("status", "failed")
                job.finished_at = datetime.now(timezone.utc)
                if result.get("detail"):
                    job.error_message = result["detail"]
                await db.commit()
    except Exception:
        # Background task should not raise - log and move on
        pass


@router.post("/api/settings/backup/run")
async def trigger_backup(
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_permission("settings", "manage")),
):
    """Trigger a manual backup run."""
    body = await request.json() if request.headers.get("content-type") == "application/json" else {}
    target = body.get("target", "primary") if isinstance(body, dict) else "primary"

    job = BackupJob(
        job_type="full",
        status="running",
        started_at=datetime.now(timezone.utc),
        target=target,
    )
    db.add(job)
    await db.flush()
    await db.refresh(job)
    job_id = job.id

    background_tasks.add_task(_run_backup_task, job_id, target)

    return {
        "status": "ok",
        "job_id": job_id,
        "message": "Backup started",
    }


@router.get("/api/settings/backup/status")
async def get_backup_status(
    _user: User = Depends(require_permission("settings", "manage")),
):
    """Get current backup system status."""
    return await backup_service.get_status()


@router.get("/api/settings/backup/retention")
async def get_retention_policy(
    _user: User = Depends(require_permission("settings", "manage")),
):
    """Get backup retention policies."""
    return {
        "retention_days": settings.BACKUP_RETENTION_DAYS,
        "schedule": settings.BACKUP_SCHEDULE,
    }


@router.post("/api/settings/backup/schedule")
async def update_backup_schedule(
    schedule: ScheduleUpdate,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_permission("settings", "manage")),
):
    """Update backup schedule configuration."""
    settings.BACKUP_SCHEDULE = schedule.cron_expression

    # Also persist to DB
    result = await db.execute(select(BackupSchedule).limit(1))
    existing = result.scalar_one_or_none()
    if existing:
        existing.cron_expression = schedule.cron_expression
        existing.is_active = schedule.is_active
    else:
        new_schedule = BackupSchedule(
            cron_expression=schedule.cron_expression,
            is_active=schedule.is_active,
        )
        db.add(new_schedule)
    await db.flush()

    return {
        "status": "ok",
        "cron_expression": schedule.cron_expression,
        "is_active": schedule.is_active,
    }
