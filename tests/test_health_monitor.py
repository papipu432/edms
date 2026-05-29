from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password
from app.models.document import Document, DocumentStatus
from app.models.group import Group
from app.models.lifecycle import DocumentLifecycle, DocumentLifecycleState, LifecycleType
from app.models.user import Role, User, UserRole
from app.schemas.health import HealthReport
from app.services.email_notifications import EmailNotificationService
from app.services.health_monitor import HealthMonitorService


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


async def _create_group(db: AsyncSession, name: str = "Test Group") -> Group:
    group = Group(name=name)
    db.add(group)
    await db.flush()
    await db.refresh(group)
    return group


async def _create_document(
    db: AsyncSession,
    group: Group,
    filename: str = "test.pdf",
    status: DocumentStatus = DocumentStatus.uploaded,
) -> Document:
    doc = Document(
        group_id=group.id,
        original_filename=filename,
        storage_path=f"/tmp/{filename}",
        file_type="application/pdf",
        file_size=1024,
        status=status,
    )
    db.add(doc)
    await db.flush()
    await db.refresh(doc)
    return doc


@pytest.mark.asyncio
async def test_detect_expired_lifecycles(db_session: AsyncSession):
    """Test that expired lifecycles are detected."""
    service = HealthMonitorService()
    group = await _create_group(db_session)
    doc = await _create_document(db_session, group, "expired_doc.pdf")

    # Create a lifecycle with an expiry date in the past
    lifecycle = DocumentLifecycle(
        document_id=doc.id,
        lifecycle_type=LifecycleType.expiring,
        state=DocumentLifecycleState.approved,
        expires_at=datetime.now(timezone.utc) - timedelta(days=10),
    )
    db_session.add(lifecycle)
    await db_session.flush()

    issues = await service.detect_expired_lifecycles(db_session)
    assert len(issues) == 1
    assert issues[0].issue_type == "expired_lifecycle"
    assert issues[0].severity == "high"
    assert issues[0].document_id == doc.id
    assert issues[0].document_name == "expired_doc.pdf"


@pytest.mark.asyncio
async def test_detect_expired_lifecycles_not_triggered_for_future(db_session: AsyncSession):
    """Test that non-expired lifecycles are not flagged."""
    service = HealthMonitorService()
    group = await _create_group(db_session)
    doc = await _create_document(db_session, group, "future_doc.pdf")

    lifecycle = DocumentLifecycle(
        document_id=doc.id,
        lifecycle_type=LifecycleType.expiring,
        state=DocumentLifecycleState.approved,
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
    )
    db_session.add(lifecycle)
    await db_session.flush()

    issues = await service.detect_expired_lifecycles(db_session)
    assert len(issues) == 0


@pytest.mark.asyncio
async def test_detect_broken_reviewer_deleted(db_session: AsyncSession):
    """Test detection of lifecycles with deleted reviewer."""
    service = HealthMonitorService()
    group = await _create_group(db_session)
    doc = await _create_document(db_session, group, "orphan_reviewer.pdf")

    # Assign a non-existent reviewer ID
    lifecycle = DocumentLifecycle(
        document_id=doc.id,
        lifecycle_type=LifecycleType.recurring,
        state=DocumentLifecycleState.in_review,
        assigned_reviewer_id="non-existent-user-id",
    )
    db_session.add(lifecycle)
    await db_session.flush()

    issues = await service.detect_broken_reviewers(db_session)
    assert len(issues) == 1
    assert issues[0].issue_type == "broken_reviewer"
    assert issues[0].severity == "high"
    assert "no longer exists" in issues[0].detail


@pytest.mark.asyncio
async def test_detect_broken_reviewer_deactivated(db_session: AsyncSession):
    """Test detection of lifecycles with deactivated reviewer."""
    service = HealthMonitorService()
    group = await _create_group(db_session)
    doc = await _create_document(db_session, group, "deactivated_reviewer.pdf")

    # Create a deactivated user
    user = User(
        username="inactive_reviewer",
        email="inactive@example.com",
        display_name="Inactive",
        hashed_password=hash_password("password123"),
        is_active=False,
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)

    lifecycle = DocumentLifecycle(
        document_id=doc.id,
        lifecycle_type=LifecycleType.recurring,
        state=DocumentLifecycleState.in_review,
        assigned_reviewer_id=user.id,
    )
    db_session.add(lifecycle)
    await db_session.flush()

    issues = await service.detect_broken_reviewers(db_session)
    assert len(issues) == 1
    assert issues[0].issue_type == "broken_reviewer"
    assert issues[0].severity == "medium"
    assert "deactivated" in issues[0].detail


@pytest.mark.asyncio
async def test_detect_empty_groups(db_session: AsyncSession):
    """Test detection of groups with no documents."""
    service = HealthMonitorService()
    await _create_group(db_session, "Empty Group")

    issues = await service.detect_empty_groups(db_session)
    assert len(issues) >= 1
    empty_group_issues = [i for i in issues if "Empty Group" in i.detail]
    assert len(empty_group_issues) == 1
    assert empty_group_issues[0].issue_type == "empty_group"
    assert empty_group_issues[0].severity == "low"


@pytest.mark.asyncio
async def test_detect_stale_documents(db_session: AsyncSession):
    """Test detection of documents stuck in processing."""
    service = HealthMonitorService()
    group = await _create_group(db_session)

    doc = Document(
        group_id=group.id,
        original_filename="stuck.pdf",
        storage_path="/tmp/stuck.pdf",
        file_type="application/pdf",
        file_size=1024,
        status=DocumentStatus.processing,
    )
    db_session.add(doc)
    await db_session.flush()
    await db_session.refresh(doc)

    # Manually set updated_at to 2 days ago
    from sqlalchemy import update
    await db_session.execute(
        update(Document)
        .where(Document.id == doc.id)
        .values(updated_at=datetime.now(timezone.utc) - timedelta(hours=48))
    )
    await db_session.flush()

    issues = await service.detect_stale_documents(db_session)
    assert len(issues) == 1
    assert issues[0].issue_type == "stale_document"
    assert issues[0].severity == "medium"
    assert issues[0].document_name == "stuck.pdf"


@pytest.mark.asyncio
async def test_full_health_check(db_session: AsyncSession):
    """Test that run_full_health_check aggregates all issues."""
    service = HealthMonitorService()
    group = await _create_group(db_session, "Health Check Group")
    doc = await _create_document(db_session, group, "expired.pdf")

    # Create expired lifecycle
    lifecycle = DocumentLifecycle(
        document_id=doc.id,
        lifecycle_type=LifecycleType.expiring,
        state=DocumentLifecycleState.approved,
        expires_at=datetime.now(timezone.utc) - timedelta(days=5),
    )
    db_session.add(lifecycle)
    await db_session.flush()

    # Create an empty group
    await _create_group(db_session, "Another Empty Group")

    report = await service.run_full_health_check(db_session)
    assert isinstance(report, HealthReport)
    assert report.checked_at is not None
    assert isinstance(report.summary, dict)
    assert len(report.issues) >= 2  # at least expired lifecycle + empty group


@pytest.mark.asyncio
async def test_health_check_api_endpoint(client: AsyncClient, db_session: AsyncSession):
    """Test the GET /api/health/check endpoint."""
    user, token = await _create_admin_user(db_session)
    group = await _create_group(db_session, "API Test Group")
    doc = await _create_document(db_session, group, "api_test.pdf")

    lifecycle = DocumentLifecycle(
        document_id=doc.id,
        lifecycle_type=LifecycleType.expiring,
        state=DocumentLifecycleState.approved,
        expires_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    db_session.add(lifecycle)
    await db_session.flush()

    response = await client.get(
        "/api/health/check",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "issues" in data
    assert "checked_at" in data
    assert "summary" in data
    assert len(data["issues"]) >= 1


@pytest.mark.asyncio
async def test_health_check_requires_admin(client: AsyncClient, db_session: AsyncSession):
    """Test that the health check endpoint requires admin role."""
    # Create a non-admin user
    existing = await db_session.execute(select(Role).where(Role.code == "editor"))
    if existing.scalar_one_or_none() is None:
        db_session.add(Role(code="editor", name="Editor", description="Editor role", is_system=True))
    await db_session.flush()

    user = User(
        username="editor_user",
        email="editor@example.com",
        display_name="Editor",
        hashed_password=hash_password("password123"),
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)

    result = await db_session.execute(select(Role).where(Role.code == "editor"))
    role = result.scalar_one()
    db_session.add(UserRole(user_id=user.id, role_id=role.id))
    await db_session.flush()
    await db_session.refresh(user)

    token = create_access_token(data={"sub": user.username})
    response = await client.get(
        "/api/health/check",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_health_dashboard_page(client: AsyncClient, db_session: AsyncSession):
    """Test that the dashboard HTML page is accessible."""
    user, token = await _create_admin_user(db_session)
    response = await client.get(
        "/settings/health",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert "Health Monitor" in response.text


@pytest.mark.asyncio
async def test_send_digest_endpoint(client: AsyncClient, db_session: AsyncSession):
    """Test the POST /api/health/send-digest endpoint."""
    user, token = await _create_admin_user(db_session)

    response = await client.post(
        "/api/health/send-digest",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "report" in data
    assert "sent_to" in data
    assert user.email in data["sent_to"]


@pytest.mark.asyncio
async def test_email_digest_formatting():
    """Test that the health digest email is properly formatted."""
    service = EmailNotificationService()
    report = HealthReport(
        issues=[
            {
                "issue_type": "expired_lifecycle",
                "severity": "high",
                "document_id": 1,
                "document_name": "test.pdf",
                "detail": "Lifecycle expired",
                "recommended_action": "Renew document",
            }
        ],
        checked_at=datetime.now(timezone.utc),
        summary={"expired_lifecycle": 1},
    )
    # Since SMTP is not configured, send_health_digest returns False but
    # it should not raise an exception
    result = service.send_health_digest(report, ["admin@example.com"])
    assert result is False  # SMTP not configured in test environment
