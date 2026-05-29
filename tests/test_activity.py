import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password
from app.models.audit import DocumentAuditLog
from app.models.document import Document, DocumentStatus
from app.models.group import Group
from app.models.user import Role, User, UserRole


async def _create_user_and_token(
    db: AsyncSession, username: str = "actuser"
) -> tuple[User, str]:
    """Create a user with admin role (grants audit:read via admin bypass)."""
    # Ensure admin role exists
    result = await db.execute(select(Role).where(Role.code == "admin"))
    role = result.scalar_one_or_none()
    if not role:
        role = Role(code="admin", name="Administrator", description="Admin role", is_system=True)
        db.add(role)
        await db.flush()
        await db.refresh(role)

    user = User(
        username=username,
        email=f"{username}@example.com",
        display_name="Activity User",
        hashed_password=hash_password("password123"),
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)

    user_role = UserRole(user_id=user.id, role_id=role.id)
    db.add(user_role)
    await db.flush()
    await db.refresh(user)

    token = create_access_token(data={"sub": user.username})
    return user, token


async def _create_document_with_audit(
    db: AsyncSession, user: User
) -> tuple[Document, list[DocumentAuditLog]]:
    group = Group(name="Activity Test Group")
    db.add(group)
    await db.flush()
    await db.refresh(group)

    doc = Document(
        group_id=group.id,
        original_filename="activity_test.pdf",
        storage_path="/tmp/activity_test.pdf",
        file_type="application/pdf",
        file_size=1024,
        status=DocumentStatus.uploaded,
    )
    db.add(doc)
    await db.flush()
    await db.refresh(doc)

    # Create audit log entries
    logs = []
    for action in ["created", "viewed", "updated"]:
        log = DocumentAuditLog(
            document_id=doc.id,
            action=action,
            actor_id=user.id,
            actor_username=user.username,
            details_json={"info": f"Document was {action}"},
        )
        db.add(log)
        logs.append(log)

    await db.flush()
    for log in logs:
        await db.refresh(log)
    return doc, logs


@pytest.mark.asyncio
async def test_global_activity_feed(client: AsyncClient, db_session: AsyncSession):
    """Test global activity feed returns audit entries."""
    user, token = await _create_user_and_token(db_session)
    doc, logs = await _create_document_with_audit(db_session, user)

    response = await client.get(
        "/api/activity/feed",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 3
    assert len(data["entries"]) >= 3

    # Entries should have expected structure
    entry = data["entries"][0]
    assert "id" in entry
    assert "document_id" in entry
    assert "action" in entry
    assert "actor_username" in entry
    assert "timestamp" in entry


@pytest.mark.asyncio
async def test_document_activity_feed(client: AsyncClient, db_session: AsyncSession):
    """Test per-document activity feed filters correctly."""
    user, token = await _create_user_and_token(db_session, username="actdoc")
    doc, logs = await _create_document_with_audit(db_session, user)

    # Create another document with its own audit
    group = Group(name="Other Activity Group")
    db_session.add(group)
    await db_session.flush()
    await db_session.refresh(group)
    other_doc = Document(
        group_id=group.id,
        original_filename="other.pdf",
        storage_path="/tmp/other.pdf",
        file_type="application/pdf",
        file_size=512,
        status=DocumentStatus.uploaded,
    )
    db_session.add(other_doc)
    await db_session.flush()
    await db_session.refresh(other_doc)
    other_log = DocumentAuditLog(
        document_id=other_doc.id,
        action="created",
        actor_id=user.id,
        actor_username=user.username,
    )
    db_session.add(other_log)
    await db_session.flush()

    # Get activity for first document only
    response = await client.get(
        f"/api/documents/{doc.id}/activity",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 3
    # All entries should belong to the specific document
    for entry in data["entries"]:
        assert entry["document_id"] == doc.id


@pytest.mark.asyncio
async def test_activity_feed_pagination(client: AsyncClient, db_session: AsyncSession):
    """Test activity feed pagination works."""
    user, token = await _create_user_and_token(db_session, username="actpage")
    _, logs = await _create_document_with_audit(db_session, user)

    # Get with limit=1
    response = await client.get(
        "/api/activity/feed?limit=1&offset=0",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["entries"]) == 1
    assert data["total"] >= 3

    # Get with offset
    response2 = await client.get(
        "/api/activity/feed?limit=1&offset=1",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response2.status_code == 200
    data2 = response2.json()
    assert len(data2["entries"]) == 1
    # Different entry
    assert data2["entries"][0]["id"] != data["entries"][0]["id"]


@pytest.mark.asyncio
async def test_document_activity_not_found(
    client: AsyncClient, db_session: AsyncSession
):
    """Test per-document activity for non-existent document returns 404."""
    _, token = await _create_user_and_token(db_session, username="actnf")

    response = await client.get(
        "/api/documents/99999/activity",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_activity_requires_auth(client: AsyncClient, db_session: AsyncSession):
    """Test activity feed requires authentication."""
    response = await client.get("/api/activity/feed")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_activity_feed_requires_audit_permission(
    client: AsyncClient, db_session: AsyncSession
):
    """Test activity feed returns 403 for user without audit:read permission."""
    # Create a regular user without admin role
    user = User(
        username="noaudit",
        email="noaudit@example.com",
        display_name="No Audit User",
        hashed_password=hash_password("password123"),
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    token = create_access_token(data={"sub": user.username})

    response = await client.get(
        "/api/activity/feed",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403
