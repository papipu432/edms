"""Health check and metrics endpoints (no authentication required)."""

import asyncio

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db

router = APIRouter(tags=["health"])


@router.get("/health")
async def liveness():
    """Liveness probe - always returns ok if the service is running."""
    return {"status": "ok"}


async def _check_redis() -> str:
    """Check Redis connectivity without blocking the event loop."""
    try:
        import redis as sync_redis

        def _ping():
            r = sync_redis.Redis.from_url(settings.REDIS_URL, socket_connect_timeout=1)
            r.ping()
            return True

        await asyncio.to_thread(_ping)
        return "ok"
    except Exception:
        return "unavailable"


@router.get("/health/ready")
async def readiness(db: AsyncSession = Depends(get_db)):
    """Readiness probe - checks database and optional Redis connectivity."""
    checks: dict[str, str] = {}

    # Check database
    try:
        await db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception:
        checks["database"] = "error"

    # Check Redis (optional, non-critical) - run in thread to avoid blocking
    checks["redis"] = await _check_redis()

    status = "ok" if checks.get("database") == "ok" else "degraded"
    return {"status": status, "checks": checks}


@router.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint."""
    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
