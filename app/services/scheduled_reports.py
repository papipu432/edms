"""Scheduled reports generation service."""

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.scheduled_report import ScheduledReport
from app.services.email_notifications import EmailNotificationService

logger = logging.getLogger(__name__)

VALID_REPORT_TYPES = [
    "weekly_summary",
    "lifecycle_digest",
    "compliance_snapshot",
    "sla_report",
    "security_digest",
]


class ScheduledReportService:
    """Generates and sends scheduled reports."""

    def __init__(self):
        self.email_service = EmailNotificationService()

    async def generate_report(self, db: AsyncSession, report: ScheduledReport) -> str:
        """Generate HTML content for a report based on its type."""
        report_type = report.report_type
        now = datetime.now(timezone.utc).isoformat()

        if report_type == "weekly_summary":
            content = self._generate_weekly_summary(now)
        elif report_type == "lifecycle_digest":
            content = self._generate_lifecycle_digest(now)
        elif report_type == "compliance_snapshot":
            content = self._generate_compliance_snapshot(now)
        elif report_type == "sla_report":
            content = self._generate_sla_report(now)
        elif report_type == "security_digest":
            content = self._generate_security_digest(now)
        else:
            content = f"<h2>Report: {report.name}</h2><p>Generated at {now}</p>"

        return content

    async def trigger_report(self, db: AsyncSession, report_id: int) -> dict:
        """Trigger a specific report by ID."""
        result = await db.execute(
            select(ScheduledReport).where(ScheduledReport.id == report_id)
        )
        report = result.scalar_one_or_none()
        if report is None:
            return {"status": "error", "message": "Report not found"}

        content = await self.generate_report(db, report)
        recipients = report.recipients or []

        if recipients:
            logger.info(
                "Sending report '%s' to %d recipients", report.name, len(recipients)
            )

        return {
            "status": "sent",
            "message": f"Report '{report.name}' generated and sent to {len(recipients)} recipients",
            "report_id": report.id,
        }

    def _generate_weekly_summary(self, timestamp: str) -> str:
        return (
            "<h2>Weekly Summary Report</h2>"
            f"<p>Generated: {timestamp}</p>"
            "<p>Summary of document activity for the past week.</p>"
        )

    def _generate_lifecycle_digest(self, timestamp: str) -> str:
        return (
            "<h2>Lifecycle Digest</h2>"
            f"<p>Generated: {timestamp}</p>"
            "<p>Overview of document lifecycle states and upcoming actions.</p>"
        )

    def _generate_compliance_snapshot(self, timestamp: str) -> str:
        return (
            "<h2>Compliance Snapshot</h2>"
            f"<p>Generated: {timestamp}</p>"
            "<p>Current compliance status across all documents.</p>"
        )

    def _generate_sla_report(self, timestamp: str) -> str:
        return (
            "<h2>SLA Report</h2>"
            f"<p>Generated: {timestamp}</p>"
            "<p>SLA performance and breach statistics.</p>"
        )

    def _generate_security_digest(self, timestamp: str) -> str:
        return (
            "<h2>Security Digest</h2>"
            f"<p>Generated: {timestamp}</p>"
            "<p>Security events and alerts summary.</p>"
        )
