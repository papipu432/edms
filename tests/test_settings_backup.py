from datetime import datetime, timezone
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select

from app.core.config import settings
from app.core.security import create_access_token, hash_password
from app.models.backup import BackupJob
from app.models.user import Role, User, UserRole


@pytest.fixture(autouse=True)
def _reset_backup_settings():
    """Reset backup settings before and after each test."""
    original = {
        "MINIO_PRIMARY_ENDPOINT": settings.MINIO_PRIMARY_ENDPOINT,
        "MINIO_PRIMARY_ACCESS_KEY": settings.MINIO_PRIMARY_ACCESS_KEY,
        "MINIO_PRIMARY_SECRET_KEY": settings.MINIO_PRIMARY_SECRET_KEY,
        "MINIO_PRIMARY_BUCKET": settings.MINIO_PRIMARY_BUCKET,
        "MINIO_DR_ENDPOINT": settings.MINIO_DR_ENDPOINT,
        "MINIO_DR_ACCESS_KEY": settings.MINIO_DR_ACCESS_KEY,
        "MINIO_DR_SECRET_KEY": settings.MINIO_DR_SECRET_KEY,
        "MINIO_DR_BUCKET": settings.MINIO_DR_BUCKET,
        "RESTIC_REPOSITORY": settings.RESTIC_REPOSITORY,
        "RESTIC_PASSWORD": settings.RESTIC_PASSWORD,
        "BACKUP_SCHEDULE": settings.BACKUP_SCHEDULE,
        "BACKUP_RETENTION_DAYS": settings.BACKUP_RETENTION_DAYS,
    }
    yield
    for key, val in original.items():
        setattr(settings, key, val)


@pytest_asyncio.fixture
async def seeded_db(db_session):
    """Seed roles into the test database."""
    roles_data = [
        ("admin", "Administrator"),
        ("manager", "Manager"),
        ("viewer", "Viewer"),
    ]
    for code, name in roles_data:
        db_session.add(Role(code=code, name=name, description=f"{code} role", is_system=True))
    await db_session.flush()
    return db_session


@pytest_asyncio.fixture
async def admin_user(seeded_db):
    """Create an admin user in the test database."""
    result = await seeded_db.execute(select(Role).where(Role.code == "admin"))
    admin_role = result.scalar_one()

    user = User(
        username="admin",
        email="admin@edms.local",
        display_name="Admin",
        hashed_password=hash_password("admin"),
    )
    seeded_db.add(user)
    await seeded_db.flush()
    await seeded_db.refresh(user)

    user_role = UserRole(user_id=user.id, role_id=admin_role.id)
    seeded_db.add(user_role)
    await seeded_db.flush()
    await seeded_db.refresh(user)
    return user


@pytest_asyncio.fixture
async def admin_token(admin_user):
    """Create a valid JWT token for the admin user."""
    return create_access_token(data={"sub": admin_user.username})


async def test_settings_backup_page_loads(client: AsyncClient, admin_token: str):
    """Test that the backup settings HTML page loads successfully."""
    resp = await client.get(
        "/settings/backup",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    assert "Backup Settings" in resp.text
    assert "MinIO Primary Storage" in resp.text
    assert "Restic Repository" in resp.text


async def test_settings_backup_page_requires_auth(client: AsyncClient):
    """Test that the settings page requires authentication."""
    resp = await client.get("/settings/backup")
    assert resp.status_code == 401


async def test_get_backup_config(client: AsyncClient, admin_token: str):
    """Test that the config endpoint returns current backup config."""
    resp = await client.get(
        "/api/settings/backup/config",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "minio_primary_endpoint" in data
    assert "minio_primary_bucket" in data
    assert "minio_dr_endpoint" in data
    assert "minio_dr_bucket" in data
    assert "restic_repository" in data
    assert "backup_schedule" in data
    assert "backup_retention_days" in data
    assert data["minio_primary_bucket"] == "edms-backup"
    assert data["minio_dr_bucket"] == "edms-backup-dr"


async def test_update_backup_config(client: AsyncClient, admin_token: str):
    """Test updating backup configuration."""
    resp = await client.post(
        "/api/settings/backup/config",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "minio_primary_endpoint": "minio.test.local:9000",
            "minio_primary_access_key": "testaccesskey",
            "minio_primary_bucket": "test-bucket",
            "backup_retention_days": 60,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"

    # Verify settings were updated
    resp = await client.get(
        "/api/settings/backup/config",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    data = resp.json()
    assert data["minio_primary_endpoint"] == "minio.test.local:9000"
    assert data["minio_primary_access_key"] == "***"
    assert data["minio_primary_bucket"] == "test-bucket"
    assert data["backup_retention_days"] == 60


async def test_backup_history_empty(client: AsyncClient, admin_token: str):
    """Test backup history endpoint returns empty list initially."""
    resp = await client.get(
        "/api/settings/backup/history",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "jobs" in data
    assert data["jobs"] == []


async def test_backup_history_with_data(client: AsyncClient, admin_token: str, db_session):
    """Test backup history endpoint with seeded data."""
    job = BackupJob(
        job_type="full",
        status="completed",
        started_at=datetime(2024, 1, 1, 2, 0, 0, tzinfo=timezone.utc),
        finished_at=datetime(2024, 1, 1, 2, 15, 0, tzinfo=timezone.utc),
        size_bytes=1024000,
        files_count=42,
        target="primary",
    )
    db_session.add(job)
    await db_session.flush()

    resp = await client.get(
        "/api/settings/backup/history",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["jobs"]) == 1
    assert data["jobs"][0]["job_type"] == "full"
    assert data["jobs"][0]["status"] == "completed"
    assert data["jobs"][0]["size_bytes"] == 1024000
    assert data["jobs"][0]["files_count"] == 42
    assert data["jobs"][0]["target"] == "primary"


@patch("app.api.settings_backup.backup_service.run_backup")
async def test_trigger_manual_backup(mock_run_backup, client: AsyncClient, admin_token: str):
    """Test triggering a manual backup creates a job."""
    mock_run_backup.return_value = {"status": "completed", "target": "primary"}

    resp = await client.post(
        "/api/settings/backup/run",
        headers={"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"},
        json={"target": "primary"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "job_id" in data
    assert data["message"] == "Backup started"


async def test_backup_status(client: AsyncClient, admin_token: str):
    """Test backup status endpoint."""
    resp = await client.get(
        "/api/settings/backup/status",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "restic_installed" in data
    assert "repository_configured" in data
    assert "primary_endpoint_configured" in data
    assert "dr_endpoint_configured" in data
    assert "schedule" in data
    assert "retention_days" in data


async def test_retention_policy(client: AsyncClient, admin_token: str):
    """Test retention policy endpoint."""
    resp = await client.get(
        "/api/settings/backup/retention",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "retention_days" in data
    assert "schedule" in data
    assert data["retention_days"] == 30


async def test_update_backup_schedule(client: AsyncClient, admin_token: str):
    """Test updating backup schedule."""
    resp = await client.post(
        "/api/settings/backup/schedule",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"cron_expression": "0 3 * * *", "is_active": True},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["cron_expression"] == "0 3 * * *"
    assert data["is_active"] is True


async def test_update_backup_schedule_persists_in_settings(client: AsyncClient, admin_token: str):
    """Test that schedule update is reflected in runtime settings."""
    await client.post(
        "/api/settings/backup/schedule",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"cron_expression": "30 4 * * 1", "is_active": True},
    )

    resp = await client.get(
        "/api/settings/backup/status",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    data = resp.json()
    assert data["schedule"] == "30 4 * * 1"
