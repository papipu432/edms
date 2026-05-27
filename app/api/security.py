"""Security monitoring API router."""

from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import PlainTextResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security import require_permission
from app.models.security import MonitoringConfig, SecurityAlert
from app.models.user import User
from app.services.notifications import get_notification_manager
from app.services.ransomware_detector import get_detector
from app.services.security_configs import (
    generate_auditd_rules,
    generate_falco_rules,
    generate_kms_audit_config,
    generate_suricata_rules,
)
from app.services.security_monitoring import (
    MonitoringAlertProcessor,
    get_kms_rate_limiter,
)

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
    def _persist_alert(alert_data: dict):
        """Persist alert from detector thread into the database."""
        from app.core.database import SessionLocal

        session = SessionLocal()
        try:
            alert = SecurityAlert(
                alert_type=alert_data.get("alert_type", "unknown"),
                severity=alert_data.get("severity", "medium"),
                message=alert_data.get("message", ""),
                details_json=alert_data.get("details"),
                source_path=alert_data.get("source_path"),
            )
            session.add(alert)
            session.commit()
        except Exception:
            session.rollback()
        finally:
            session.close()

    detector.set_alert_callback(_persist_alert)
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


# ---- Security Monitoring Layer endpoints ----


class AlertIngestBody(BaseModel):
    source: str
    severity: str
    message: str
    details: dict | None = None


@router.get("/api/security/monitoring/status")
async def get_monitoring_status(
    _user: User = Depends(require_permission("security", "manage")),
):
    """Return current status of all monitoring layers."""
    processor = MonitoringAlertProcessor()
    return processor.get_monitoring_status()


@router.post("/api/security/monitoring/alerts/ingest")
async def ingest_monitoring_alert(
    body: AlertIngestBody,
    _user: User = Depends(require_permission("security", "manage")),
    db: AsyncSession = Depends(get_db),
    x_webhook_secret: str | None = Header(None),
):
    """Webhook endpoint to receive alerts from external monitoring tools."""
    # Validate webhook secret if configured
    if settings.SECURITY_MONITORING_WEBHOOK_SECRET:
        if x_webhook_secret != settings.SECURITY_MONITORING_WEBHOOK_SECRET:
            return {"status": "error", "message": "Invalid webhook secret"}

    processor = MonitoringAlertProcessor()
    alert_data = {
        "source": body.source,
        "severity": body.severity,
        "message": body.message,
        "details": body.details,
    }

    try:
        alert = await processor.process_external_alert(db, alert_data)
    except ValueError as e:
        from fastapi import HTTPException

        raise HTTPException(status_code=422, detail=str(e))

    # Send notification via NotificationManager
    notifier = get_notification_manager()
    await notifier.create_notification(
        db=db,
        user_id=None,
        notification_type="security_monitoring_alert",
        title=f"Security Alert: {body.source}",
        message=body.message,
        data={"alert_id": alert.id, "source": body.source, "severity": body.severity},
    )

    return {"status": "ok", "alert_id": alert.id}


@router.get("/api/security/monitoring/configs/{tool}")
async def get_monitoring_config(
    tool: str,
    _user: User = Depends(require_permission("security", "manage")),
):
    """Return generated configuration for the specified monitoring tool."""
    generators = {
        "auditd": generate_auditd_rules,
        "falco": generate_falco_rules,
        "suricata": generate_suricata_rules,
        "kms_audit": generate_kms_audit_config,
    }

    if tool not in generators:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=404,
            detail=f"Unknown tool: {tool}. Available: {list(generators.keys())}",
        )

    content = generators[tool]()
    return PlainTextResponse(content=content)


@router.get("/api/security/kms/rate-limit-status")
async def get_kms_rate_limit_status(
    _user: User = Depends(require_permission("security", "manage")),
):
    """Return current KMS rate limiter status."""
    rate_limiter = get_kms_rate_limiter()
    return rate_limiter.get_status()
