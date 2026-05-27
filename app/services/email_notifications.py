import logging
import smtplib
from email.mime.text import MIMEText

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.services.lifecycle import LifecycleService

logger = logging.getLogger(__name__)


class EmailNotificationService:
    def __init__(self):
        self.smtp_host = settings.SMTP_HOST
        self.smtp_port = settings.SMTP_PORT
        self.smtp_user = settings.SMTP_USER
        self.smtp_password = settings.SMTP_PASSWORD
        self.from_email = settings.SMTP_FROM_EMAIL

    def send_lifecycle_alert(
        self,
        to_email: str,
        document_name: str,
        alert_type: str,
        days_remaining: int,
    ) -> bool:
        subject = f"Document Lifecycle Alert: {document_name}"
        if alert_type == "expiry":
            body = (
                f"Document '{document_name}' is expiring in {days_remaining} days. "
                "Please take appropriate action."
            )
        else:
            body = (
                f"Document '{document_name}' is due for review in {days_remaining} days. "
                "Please schedule a review."
            )

        if not self.smtp_host:
            logger.info(
                "SMTP not configured. Alert: %s for '%s' (%d days remaining)",
                alert_type,
                document_name,
                days_remaining,
            )
            return False

        try:
            msg = MIMEText(body)
            msg["Subject"] = subject
            msg["From"] = self.from_email
            msg["To"] = to_email

            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                if self.smtp_user and self.smtp_password:
                    server.starttls()
                    server.login(self.smtp_user, self.smtp_password)
                server.send_message(msg)
            return True
        except Exception:
            logger.exception("Failed to send lifecycle alert email to %s", to_email)
            return False

    async def check_and_send_alerts(self, db: AsyncSession) -> int:
        lifecycle_service = LifecycleService()
        alerts = await lifecycle_service.get_alerts(
            db,
            days_before_expiry=settings.ALERT_DAYS_BEFORE_EXPIRY,
            days_before_review=settings.ALERT_DAYS_BEFORE_REVIEW,
        )

        count = 0
        for alert in alerts:
            document_name = alert["document_name"]
            alert_type = alert["alert_type"]
            days_remaining = alert["days_remaining"]

            # For simplicity, log alerts. In a full implementation,
            # we would look up assigned users via FolderAssignment
            # and send to each user's email.
            self.send_lifecycle_alert(
                to_email=self.from_email,
                document_name=document_name,
                alert_type=alert_type,
                days_remaining=days_remaining,
            )
            count += 1

        return count
