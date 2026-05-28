"""Celery tasks for email notifications."""

from celery.utils.log import get_task_logger

from app.tasks import celery_app

logger = get_task_logger(__name__)


@celery_app.task(name="app.tasks.notifications.send_lifecycle_alert_task")
def send_lifecycle_alert_task(
    to_email: str, document_name: str, alert_type: str, days_remaining: int
) -> None:
    """Send a lifecycle alert email."""
    from app.services.email_notifications import EmailNotificationService

    service = EmailNotificationService()
    service.send_lifecycle_alert(to_email, document_name, alert_type, days_remaining)
    logger.info(
        "Lifecycle alert sent: %s for '%s' to %s", alert_type, document_name, to_email
    )


@celery_app.task(name="app.tasks.notifications.send_health_digest_task")
def send_health_digest_task(to_email: str, report_data: dict) -> None:
    """Send a health digest email."""
    from app.services.email_notifications import EmailNotificationService

    service = EmailNotificationService()
    service.send_health_digest(to_email, report_data)
    logger.info("Health digest sent to %s", to_email)
