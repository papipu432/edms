"""Tests for health score dashboard endpoints."""

from datetime import date

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password
from app.models.document import Document, DocumentStatus
from app.models.group import Group
from app.models.health_score import HealthScoreRecord
from app.models.user import Role, User, UserRole
from app.services.health_score import HealthScoreService


async def _create_admin_user(db: AsyncSession, username: str = "admin") -> tuple[User, str]:
    """Create an admin user and return (user, token)."""
    existing = await db.execute(select(Role).where(Role.code == "admin"))
    if existing.scalar_one_or_none() is None:
        db.add(Role(code="admin", name="Admin", description="Admin role", is_system=True))
    await db.flush()

    user = User(
        username=username,
        email=f"{username}@example.com",
        display_name="Admin User",
        hashed_password=hash_password("password123"),
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)

    result = await db.execute(select(Role).where(Role.code == "admin"))
    role = result.scalar_one()
    user_role = UserRole(user_id=user.id, role_id=role.id)
    db.add(user_role)
    await db.flush()
    await db.refresh(user)

    token = create_access_token(data={"sub": user.username})
    return user, token


@pytest.mark.asyncio
async def test_health_score_endpoint(client: AsyncClient, db_session: AsyncSession):
    """Test GET /api/health/score returns composite score and components."""
    _, token = await _create_admin_user(db_session)

    response = await client.get(
        "/api/health/score",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "composite_score" in data
    assert "components" in data
    assert 0 <= data["composite_score"] <= 100
    assert len(data["components"]) == 6


@pytest.mark.asyncio
async def test_health_score_components_in_range(client: AsyncClient, db_session: AsyncSession):
    """Test that all component scores are between 0 and 100."""
    _, token = await _create_admin_user(db_session)

    response = await client.get(
        "/api/health/score",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    for component in data["components"]:
        assert 0 <= component["score"] <= 100
        assert "name" in component
        assert "detail" in component


@pytest.mark.asyncio
async def test_health_score_history_empty(client: AsyncClient, db_session: AsyncSession):
    """Test GET /api/health/score/history returns empty list when no records."""
    _, token = await _create_admin_user(db_session)

    response = await client.get(
        "/api/health/score/history",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "history" in data
    assert data["history"] == []


@pytest.mark.asyncio
async def test_health_score_history_with_records(client: AsyncClient, db_session: AsyncSession):
    """Test GET /api/health/score/history returns stored records."""
    _, token = await _create_admin_user(db_session)

    # Create a history record
    record = HealthScoreRecord(
        date=date.today(),
        composite_score=85.5,
        orphan_score=90.0,
        lifecycle_score=80.0,
        backup_score=80.0,
        security_score=100.0,
        storage_score=80.0,
        sla_score=75.0,
    )
    db_session.add(record)
    await db_session.flush()

    response = await client.get(
        "/api/health/score/history",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["history"]) == 1
    assert data["history"][0]["composite_score"] == 85.5


@pytest.mark.asyncio
async def test_health_score_service_compute(db_session: AsyncSession):
    """Test HealthScoreService.compute_score returns valid scores."""
    service = HealthScoreService()
    scores = await service.compute_score(db_session)

    assert "composite_score" in scores
    assert "orphan_score" in scores
    assert "lifecycle_score" in scores
    assert "backup_score" in scores
    assert "security_score" in scores
    assert "storage_score" in scores
    assert "sla_score" in scores

    for key, value in scores.items():
        assert 0 <= value <= 100, f"{key} out of range: {value}"


@pytest.mark.asyncio
async def test_health_score_requires_admin(client: AsyncClient, db_session: AsyncSession):
    """Test that health score endpoints require admin role."""
    # Non-admin user
    user = User(
        username="regular",
        email="regular@example.com",
        display_name="Regular User",
        hashed_password=hash_password("password123"),
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)

    token = create_access_token(data={"sub": user.username})

    response = await client.get(
        "/api/health/score",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_health_score_page(client: AsyncClient, db_session: AsyncSession):
    """Test that the health score dashboard page renders."""
    response = await client.get("/pages/health-score")
    assert response.status_code == 200
    assert "Health Score Dashboard" in response.text
