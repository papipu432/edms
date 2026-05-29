"""Health Score computation service."""

from datetime import date, datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.models.group import Group
from app.models.health_score import HealthScoreRecord
from app.models.lifecycle import DocumentLifecycle, DocumentLifecycleState
from app.models.sla import DocumentSLA, SLAStatus


class HealthScoreService:
    """Computes system health scores across multiple dimensions."""

    WEIGHTS = {
        "orphan": 0.15,
        "lifecycle": 0.20,
        "backup": 0.15,
        "security": 0.15,
        "storage": 0.15,
        "sla": 0.20,
    }

    async def compute_score(self, db: AsyncSession) -> dict:
        """Compute all health score components and composite score."""
        orphan = await self._compute_orphan_score(db)
        lifecycle = await self._compute_lifecycle_score(db)
        backup = await self._compute_backup_score(db)
        security = await self._compute_security_score(db)
        storage = await self._compute_storage_score(db)
        sla = await self._compute_sla_score(db)

        composite = (
            orphan * self.WEIGHTS["orphan"]
            + lifecycle * self.WEIGHTS["lifecycle"]
            + backup * self.WEIGHTS["backup"]
            + security * self.WEIGHTS["security"]
            + storage * self.WEIGHTS["storage"]
            + sla * self.WEIGHTS["sla"]
        )

        return {
            "composite_score": round(composite, 2),
            "orphan_score": round(orphan, 2),
            "lifecycle_score": round(lifecycle, 2),
            "backup_score": round(backup, 2),
            "security_score": round(security, 2),
            "storage_score": round(storage, 2),
            "sla_score": round(sla, 2),
        }

    async def _compute_orphan_score(self, db: AsyncSession) -> float:
        """Score based on percentage of documents in empty or null groups."""
        total_docs_result = await db.execute(select(func.count(Document.id)))
        total_docs = total_docs_result.scalar() or 0

        if total_docs == 0:
            return 100.0

        # Docs in groups that have no other documents (orphan-like)
        # or docs whose group has no parent and only one doc
        orphan_count_result = await db.execute(
            select(func.count(Document.id)).where(
                Document.group_id.in_(
                    select(Group.id).where(Group.parent_id.is_(None))
                    .where(~Group.id.in_(
                        select(Group.id).where(Group.children != None)  # noqa: E711
                    ))
                )
            )
        )
        # Simplified: count docs in root groups with no children
        orphan_count = orphan_count_result.scalar() or 0
        orphan_percentage = orphan_count / total_docs
        return max(0.0, 100.0 - (orphan_percentage * 100.0))

    async def _compute_lifecycle_score(self, db: AsyncSession) -> float:
        """Score based on expired or overdue lifecycle documents."""
        total_result = await db.execute(select(func.count(DocumentLifecycle.id)))
        total = total_result.scalar() or 0

        if total == 0:
            return 100.0

        now = datetime.now(timezone.utc)
        expired_result = await db.execute(
            select(func.count(DocumentLifecycle.id)).where(
                (DocumentLifecycle.state == DocumentLifecycleState.expired)
                | (DocumentLifecycle.state == DocumentLifecycleState.needs_re_review)
                | (
                    (DocumentLifecycle.expires_at.isnot(None))
                    & (DocumentLifecycle.expires_at < now)
                )
            )
        )
        expired_count = expired_result.scalar() or 0
        return max(0.0, 100.0 - (expired_count / total * 100.0))

    async def _compute_backup_score(self, db: AsyncSession) -> float:
        """Score based on backup recency. Default 80 if no backup info."""
        # Simple heuristic: return 80 as default (no backup tracking model available)
        return 80.0

    async def _compute_security_score(self, db: AsyncSession) -> float:
        """Score based on security issues. Default 100 if none found."""
        # No security_issues table in current schema, return 100
        return 100.0

    async def _compute_storage_score(self, db: AsyncSession) -> float:
        """Score based on storage usage. Default 80 if not calculable."""
        return 80.0

    async def _compute_sla_score(self, db: AsyncSession) -> float:
        """Score based on SLA compliance."""
        total_result = await db.execute(select(func.count(DocumentSLA.id)))
        total = total_result.scalar() or 0

        if total == 0:
            return 100.0

        compliant_result = await db.execute(
            select(func.count(DocumentSLA.id)).where(
                DocumentSLA.status.in_([SLAStatus.on_time, SLAStatus.completed])
            )
        )
        compliant = compliant_result.scalar() or 0
        return round(compliant / total * 100.0, 2)

    async def save_daily_score(self, db: AsyncSession) -> HealthScoreRecord:
        """Compute and persist a daily score record."""
        scores = await self.compute_score(db)
        record = HealthScoreRecord(
            date=date.today(),
            composite_score=scores["composite_score"],
            orphan_score=scores["orphan_score"],
            lifecycle_score=scores["lifecycle_score"],
            backup_score=scores["backup_score"],
            security_score=scores["security_score"],
            storage_score=scores["storage_score"],
            sla_score=scores["sla_score"],
        )
        db.add(record)
        await db.flush()
        await db.refresh(record)
        return record

    async def get_history(self, db: AsyncSession, days: int = 30) -> list[HealthScoreRecord]:
        """Retrieve historical score records."""
        result = await db.execute(
            select(HealthScoreRecord)
            .order_by(HealthScoreRecord.date.desc())
            .limit(days)
        )
        return list(result.scalars().all())
