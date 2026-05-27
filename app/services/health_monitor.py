from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document, DocumentStatus
from app.models.group import Group
from app.models.lifecycle import DocumentLifecycle
from app.models.user import User
from app.schemas.health import HealthIssue, HealthReport


class HealthMonitorService:
    async def detect_expired_lifecycles(self, db: AsyncSession) -> list[HealthIssue]:
        """Find documents with lifecycles past their expiry date."""
        now = datetime.now(timezone.utc)
        result = await db.execute(
            select(DocumentLifecycle, Document)
            .join(Document, Document.id == DocumentLifecycle.document_id)
            .where(
                DocumentLifecycle.expires_at.isnot(None),
                DocumentLifecycle.expires_at < now,
            )
        )
        issues = []
        for lifecycle, document in result.all():
            issues.append(
                HealthIssue(
                    issue_type="expired_lifecycle",
                    severity="high",
                    document_id=document.id,
                    document_name=document.original_filename,
                    detail=f"Lifecycle expired on {lifecycle.expires_at.isoformat()}",
                    recommended_action="Renew or archive the document lifecycle",
                )
            )
        return issues

    async def detect_broken_reviewers(self, db: AsyncSession) -> list[HealthIssue]:
        """Find lifecycles assigned to deleted or deactivated users."""
        result = await db.execute(
            select(DocumentLifecycle, Document)
            .join(Document, Document.id == DocumentLifecycle.document_id)
            .where(DocumentLifecycle.assigned_reviewer_id.isnot(None))
        )
        issues = []
        for lifecycle, document in result.all():
            reviewer = await db.get(User, lifecycle.assigned_reviewer_id)
            if reviewer is None:
                issues.append(
                    HealthIssue(
                        issue_type="broken_reviewer",
                        severity="high",
                        document_id=document.id,
                        document_name=document.original_filename,
                        detail="Assigned reviewer no longer exists",
                        recommended_action="Reassign a new reviewer to this document",
                    )
                )
            elif not reviewer.is_active:
                issues.append(
                    HealthIssue(
                        issue_type="broken_reviewer",
                        severity="medium",
                        document_id=document.id,
                        document_name=document.original_filename,
                        detail=f"Assigned reviewer '{reviewer.username}' is deactivated",
                        recommended_action="Reassign a new active reviewer to this document",
                    )
                )
        return issues

    async def detect_empty_groups(self, db: AsyncSession) -> list[HealthIssue]:
        """Find groups with no documents."""
        result = await db.execute(select(Group))
        issues = []
        for group in result.scalars().all():
            doc_result = await db.execute(
                select(Document.id).where(Document.group_id == group.id).limit(1)
            )
            if doc_result.scalar_one_or_none() is None:
                issues.append(
                    HealthIssue(
                        issue_type="empty_group",
                        severity="low",
                        document_id=None,
                        document_name=None,
                        detail=f"Group '{group.name}' (id={group.id}) has no documents",
                        recommended_action="Add documents to the group or remove the empty group",
                    )
                )
        return issues

    async def detect_stale_documents(self, db: AsyncSession) -> list[HealthIssue]:
        """Find documents stuck in 'processing' status for over 24 hours."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        result = await db.execute(
            select(Document).where(
                Document.status == DocumentStatus.processing,
                Document.updated_at < cutoff,
            )
        )
        issues = []
        for document in result.scalars().all():
            issues.append(
                HealthIssue(
                    issue_type="stale_document",
                    severity="medium",
                    document_id=document.id,
                    document_name=document.original_filename,
                    detail="Document has been stuck in 'processing' status for over 24 hours",
                    recommended_action="Retry document processing or mark as failed",
                )
            )
        return issues

    async def run_full_health_check(self, db: AsyncSession) -> HealthReport:
        """Aggregate all health checks into a single report."""
        all_issues: list[HealthIssue] = []

        all_issues.extend(await self.detect_expired_lifecycles(db))
        all_issues.extend(await self.detect_broken_reviewers(db))
        all_issues.extend(await self.detect_empty_groups(db))
        all_issues.extend(await self.detect_stale_documents(db))

        summary: dict[str, int] = {}
        for issue in all_issues:
            summary[issue.issue_type] = summary.get(issue.issue_type, 0) + 1

        return HealthReport(
            issues=all_issues,
            checked_at=datetime.now(timezone.utc),
            summary=summary,
        )
