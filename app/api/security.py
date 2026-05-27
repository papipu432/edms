"""Security monitoring API router."""

from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import require_permission
from app.models.security import MonitoringConfig, SecurityAlert
from app.models.user import User
from app.services.ransomware_detector import get_detector

router = APIRouter(tags=["security"])
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


class ConfigUpdate(BaseModel):
    threshold_ops_per_sec: int | None = None
    window_seconds: int | None = None
    monitored_dir: str | None = None


@router.get("/settings/security")
async def settings_security_page(
    request: Request,
    _user: User = Depends(require_permission("security", "manage")),
):
    """Render the Security monitoring HTML page."""
    return templates.TemplateResponse(request, "settings_security.html")


@router.get("/api/security/status")
async def get_security_status(
    _user: User = Depends(require_permission("security", "manage")),
    db: AsyncSession = Depends(get_db),
):
    """Get current monitoring status."""
    detector = get_detector()
    status = detector.get_status()

    # Get total alert count from DB
    result = await db.execute(select(SecurityAlert))
    alerts = result.scalars().all()
    status["alerts_total"] = len(alerts)

    return status


@router.get("/api/security/alerts")
async def get_security_alerts(
    limit: int = 50,
    offset: int = 0,
    _user: User = Depends(require_permission("security", "manage")),
    db: AsyncSession = Depends(get_db),
):
    """List security alerts with pagination."""
    result = await db.execute(
        select(SecurityAlert)
        .order_by(SecurityAlert.detected_at.desc())
        .limit(limit)
        .offset(offset)
    )
    alerts = result.scalars().all()
    return {
        "alerts": [
            {
                "id": alert.id,
                "alert_type": alert.alert_type,
                "severity": alert.severity,
                "message": alert.message,
                "details_json": alert.details_json,
                "source_path": alert.source_path,
                "detected_at": alert.detected_at.isoformat() if alert.detected_at else None,
                "acknowledged": alert.acknowledged,
                "acknowledged_by": alert.acknowledged_by,
                "acknowledged_at": (
                    alert.acknowledged_at.isoformat() if alert.acknowledged_at else None
                ),
            }
            for alert in alerts
        ],
        "limit": limit,
        "offset": offset,
    }


@router.post("/api/security/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(
    alert_id: str,
    user: User = Depends(require_permission("security", "manage")),
    db: AsyncSession = Depends(get_db),
):
    """Acknowledge a security alert."""
    result = await db.execute(
        select(SecurityAlert).where(SecurityAlert.id == alert_id)
    )
    alert = result.scalar_one_or_none()
    if alert is None:
        return {"status": "error", "message": "Alert not found"}

    alert.acknowledged = True
    alert.acknowledged_by = user.id
    alert.acknowledged_at = datetime.now(timezone.utc)
    await db.flush()

    return {"status": "ok", "alert_id": alert_id}


@router.post("/api/security/monitor/start")
async def start_monitor(
    _user: User = Depends(require_permission("security", "manage")),
    db: AsyncSession = Depends(get_db),
):
    """Start the ransomware detector monitoring."""
    detector = get_detector()

    # Set up alert callback to persist alerts to DB
    async def _persist_alert(alert_data: dict):
        """This is called from the detector thread - we just store for now."""
        pass

    result = detector.start()
    return result


@router.post("/api/security/monitor/stop")
async def stop_monitor(
    _user: User = Depends(require_permission("security", "manage")),
):
    """Stop the ransomware detector monitoring."""
    detector = get_detector()
    result = detector.stop()
    return result


@router.get("/api/security/config")
async def get_security_config(
    _user: User = Depends(require_permission("security", "manage")),
    db: AsyncSession = Depends(get_db),
):
    """Get current security monitoring configuration."""
    detector = get_detector()
    return {
        "threshold_ops_per_sec": detector.threshold_ops_per_sec,
        "window_seconds": detector.window_seconds,
        "monitored_dir": str(detector.data_dir),
        "quarantine_dir": str(detector.quarantine_dir),
    }


@router.post("/api/security/config")
async def update_security_config(
    config: ConfigUpdate,
    _user: User = Depends(require_permission("security", "manage")),
    db: AsyncSession = Depends(get_db),
):
    """Update security monitoring configuration."""
    detector = get_detector()

    if config.threshold_ops_per_sec is not None:
        detector.threshold_ops_per_sec = config.threshold_ops_per_sec
        await _save_config(db, "threshold_ops_per_sec", str(config.threshold_ops_per_sec))

    if config.window_seconds is not None:
        detector.window_seconds = config.window_seconds
        await _save_config(db, "window_seconds", str(config.window_seconds))

    if config.monitored_dir is not None:
        detector.data_dir = Path(config.monitored_dir)
        await _save_config(db, "monitored_dir", config.monitored_dir)

    await db.flush()
    return {"status": "ok"}


async def _save_config(db: AsyncSession, key: str, value: str) -> None:
    """Save or update a monitoring config value in the database."""
    result = await db.execute(
        select(MonitoringConfig).where(MonitoringConfig.config_key == key)
    )
    existing = result.scalar_one_or_none()
    if existing:
        existing.config_value = value
        existing.updated_at = datetime.now(timezone.utc)
    else:
        entry = MonitoringConfig(config_key=key, config_value=value)
        db.add(entry)
