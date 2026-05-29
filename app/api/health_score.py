"""Health Score Dashboard API endpoints."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import require_role
from app.models.user import User
from app.schemas.health_score import (
    HealthScoreComponent,
    HealthScoreHistoryItem,
    HealthScoreHistoryResponse,
    HealthScoreResponse,
)
from app.services.health_score import HealthScoreService

router = APIRouter(tags=["health-score"])

health_score_service = HealthScoreService()


@router.get("/api/health/score", response_model=HealthScoreResponse)
async def get_health_score(
    _user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    """Get the current composite health score with component breakdown."""
    scores = await health_score_service.compute_score(db)

    components = [
        HealthScoreComponent(
            name="orphan",
            score=scores["orphan_score"],
            detail="Documents in empty or root-only groups",
        ),
        HealthScoreComponent(
            name="lifecycle",
            score=scores["lifecycle_score"],
            detail="Expired or overdue lifecycle documents",
        ),
        HealthScoreComponent(
            name="backup",
            score=scores["backup_score"],
            detail="Backup recency and availability",
        ),
        HealthScoreComponent(
            name="security",
            score=scores["security_score"],
            detail="Security issues and alerts",
        ),
        HealthScoreComponent(
            name="storage",
            score=scores["storage_score"],
            detail="Storage utilization",
        ),
        HealthScoreComponent(
            name="sla",
            score=scores["sla_score"],
            detail="SLA compliance rate",
        ),
    ]

    return HealthScoreResponse(
        composite_score=scores["composite_score"],
        components=components,
        computed_at=datetime.now(timezone.utc),
    )


@router.get("/api/health/score/history", response_model=HealthScoreHistoryResponse)
async def get_health_score_history(
    days: int = 30,
    _user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    """Get historical health score data."""
    records = await health_score_service.get_history(db, days=days)

    history = [
        HealthScoreHistoryItem(
            date=r.date,
            composite_score=r.composite_score,
            orphan_score=r.orphan_score,
            lifecycle_score=r.lifecycle_score,
            backup_score=r.backup_score,
            security_score=r.security_score,
            storage_score=r.storage_score,
            sla_score=r.sla_score,
        )
        for r in records
    ]

    return HealthScoreHistoryResponse(history=history)
