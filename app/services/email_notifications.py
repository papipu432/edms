import logging
import smtplib
from email.mime.text import MIMEText

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.lifecycle import DocumentLifecycle
from app.models.user import User
from app.schemas.health import HealthReport
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
            lifecycle_id = alert["lifecycle_id"]

            # Resolve the assigned reviewer's email from the lifecycle record
            to_email = self.from_email
            lifecycle = await db.get(DocumentLifecycle, lifecycle_id)
            if lifecycle and lifecycle.assigned_reviewer_id:
                reviewer = await db.get(User, lifecycle.assigned_reviewer_id)
                if reviewer and reviewer.email:
                    to_email = reviewer.email

            self.send_lifecycle_alert(
                to_email=to_email,
                document_name=document_name,
                alert_type=alert_type,
                days_remaining=days_remaining,
            )
            count += 1

        return count

    def send_health_digest(self, report: HealthReport, recipients: list[str]) -> bool:
        """Format and send a health digest email to recipients."""
        if not report.issues:
            subject = "EDMS Health Digest: All Clear"
            body_lines = ["<h2>EDMS Health Check Report</h2>", "<p>No issues detected. System is healthy.</p>"]
        else:
            subject = f"EDMS Health Digest: {len(report.issues)} issue(s) found"
            body_lines = [
                "<h2>EDMS Health Check Report</h2>",
                f"<p>Checked at: {report.checked_at.isoformat()}</p>",
                "<h3>Summary</h3><ul>",
            ]
            for issue_type, count in report.summary.items():
                body_lines.append(f"<li>{issue_type}: {count}</li>")
            body_lines.append("</ul><h3>Issues</h3><table border='1' cellpadding='4'>")
            body_lines.append("<tr><th>Document</th><th>Type</th><th>Severity</th><th>Detail</th><th>Action</th></tr>")
            for issue in report.issues:
                doc_name = issue.document_name or "-"
                body_lines.append(
                    f"<tr><td>{doc_name}</td><td>{issue.issue_type}</td>"
                    f"<td>{issue.severity}</td><td>{issue.detail}</td>"
                    f"<td>{issue.recommended_action}</td></tr>"
                )
            body_lines.append("</table>")

        body = "\n".join(body_lines)

        if not self.smtp_host:
            logger.info(
                "SMTP not configured. Health digest: %d issues for %d recipients",
                len(report.issues),
                len(recipients),
            )
            return False

        try:
            msg = MIMEText(body, "html")
            msg["Subject"] = subject
            msg["From"] = self.from_email
            msg["To"] = ", ".join(recipients)

            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                if self.smtp_user and self.smtp_password:
                    server.starttls()
                    server.login(self.smtp_user, self.smtp_password)
                server.send_message(msg)
            return True
        except Exception:
            logger.exception("Failed to send health digest email")
            return False
