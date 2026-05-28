"""Tests for scheduled reports endpoints."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password
from app.models.scheduled_report import ScheduledReport
from app.models.user import Role, User, UserRole


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
async def test_create_report(client: AsyncClient, db_session: AsyncSession):
    """Test creating a scheduled report."""
    _, token = await _create_admin_user(db_session)

    response = await client.post(
        "/api/reports",
        json={
            "name": "Weekly Summary",
            "schedule": "0 9 * * 1",
            "report_type": "weekly_summary",
            "recipients": ["admin@example.com"],
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Weekly Summary"
    assert data["report_type"] == "weekly_summary"
    assert data["is_active"] is True


@pytest.mark.asyncio
async def test_list_reports(client: AsyncClient, db_session: AsyncSession):
    """Test listing scheduled reports."""
    _, token = await _create_admin_user(db_session)

    # Create a report first
    report = ScheduledReport(
        name="Test Report",
        schedule="0 0 * * *",
        report_type="lifecycle_digest",
        recipients=["test@example.com"],
    )
    db_session.add(report)
    await db_session.flush()

    response = await client.get(
        "/api/reports",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1


@pytest.mark.asyncio
async def test_get_report(client: AsyncClient, db_session: AsyncSession):
    """Test getting a single report."""
    _, token = await _create_admin_user(db_session)

    report = ScheduledReport(
        name="Get Report",
        schedule="0 0 * * *",
        report_type="sla_report",
        recipients=["test@example.com"],
    )
    db_session.add(report)
    await db_session.flush()
    await db_session.refresh(report)

    response = await client.get(
        f"/api/reports/{report.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Get Report"


@pytest.mark.asyncio
async def test_update_report(client: AsyncClient, db_session: AsyncSession):
    """Test updating a scheduled report."""
    _, token = await _create_admin_user(db_session)

    report = ScheduledReport(
        name="Old Name",
        schedule="0 0 * * *",
        report_type="security_digest",
        recipients=["test@example.com"],
    )
    db_session.add(report)
    await db_session.flush()
    await db_session.refresh(report)

    response = await client.put(
        f"/api/reports/{report.id}",
        json={"name": "New Name"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "New Name"


@pytest.mark.asyncio
async def test_delete_report(client: AsyncClient, db_session: AsyncSession):
    """Test deleting a scheduled report."""
    _, token = await _create_admin_user(db_session)

    report = ScheduledReport(
        name="Delete Me",
        schedule="0 0 * * *",
        report_type="compliance_snapshot",
        recipients=["test@example.com"],
    )
    db_session.add(report)
    await db_session.flush()
    await db_session.refresh(report)

    response = await client.delete(
        f"/api/reports/{report.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 204


@pytest.mark.asyncio
async def test_trigger_report(client: AsyncClient, db_session: AsyncSession):
    """Test triggering a report manually."""
    _, token = await _create_admin_user(db_session)

    report = ScheduledReport(
        name="Trigger Report",
        schedule="0 0 * * *",
        report_type="weekly_summary",
        recipients=["admin@example.com"],
    )
    db_session.add(report)
    await db_session.flush()
    await db_session.refresh(report)

    response = await client.post(
        f"/api/reports/{report.id}/trigger",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "sent"
    assert data["report_id"] == report.id


@pytest.mark.asyncio
async def test_trigger_nonexistent_report(client: AsyncClient, db_session: AsyncSession):
    """Test triggering a nonexistent report returns 404."""
    _, token = await _create_admin_user(db_session)

    response = await client.post(
        "/api/reports/99999/trigger",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404
