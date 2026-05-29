"""Health monitoring dashboard API router."""

from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import require_role
from app.models.user import User
from app.schemas.health import HealthDigest, HealthReport
from app.services.email_notifications import EmailNotificationService
from app.services.health_monitor import HealthMonitorService

router = APIRouter(tags=["health"])
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))

health_monitor = HealthMonitorService()


@router.get("/api/health/check", response_model=HealthReport)
async def run_health_check(
    _user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    """Run a full health check and return the report."""
    report = await health_monitor.run_full_health_check(db)
    return report


@router.get("/settings/health")
async def health_dashboard_page(
    request: Request,
    _user: User = Depends(require_role("admin")),
):
    """Render the Health monitoring dashboard HTML page."""
    return templates.TemplateResponse(request, "health_dashboard.html")


@router.post("/api/health/send-digest", response_model=HealthDigest)
async def send_health_digest(
    _user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    """Run health check and send email digest to all admin users."""
    report = await health_monitor.run_full_health_check(db)

    # Find all admin users to send digest to
    result = await db.execute(select(User).where(User.is_active.is_(True)))
    all_users = result.scalars().all()
    admin_emails = []
    for user in all_users:
        if "admin" in user.role_codes and user.email:
            admin_emails.append(user.email)

    email_service = EmailNotificationService()
    email_service.send_health_digest(report, admin_emails)

    return HealthDigest(report=report, sent_to=admin_emails)
