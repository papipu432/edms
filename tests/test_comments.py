import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password
from app.models.document import Document, DocumentStatus
from app.models.group import Group
from app.models.notification import Notification
from app.models.user import Role, User, UserRole


async def _create_user_with_roles(
    db: AsyncSession, roles: list[str] | None = None, username: str = "testuser"
) -> tuple[User, str]:
    """Helper to create a user with specified roles and return (user, token)."""
    if roles:
        for role_code in roles:
            existing = await db.execute(select(Role).where(Role.code == role_code))
            if existing.scalar_one_or_none() is None:
                db.add(Role(code=role_code, name=role_code.title(), description=f"{role_code} role", is_system=True))
        await db.flush()

    user = User(
        username=username,
        email=f"{username}@example.com",
        display_name=username.title(),
        hashed_password=hash_password("password123"),
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)

    if roles:
        for role_code in roles:
            result = await db.execute(select(Role).where(Role.code == role_code))
            role = result.scalar_one()
            user_role = UserRole(user_id=user.id, role_id=role.id)
            db.add(user_role)
        await db.flush()
        await db.refresh(user)

    token = create_access_token(data={"sub": user.username})
    return user, token


async def _create_document(db: AsyncSession) -> Document:
    """Helper to create a group and document."""
    group = Group(name="Test Group")
    db.add(group)
    await db.flush()
    await db.refresh(group)
    doc = Document(
        group_id=group.id,
        original_filename="test.pdf",
        storage_path="/tmp/test.pdf",
        file_type="application/pdf",
        file_size=1024,
        status=DocumentStatus.uploaded,
    )
    db.add(doc)
    await db.flush()
    await db.refresh(doc)
    return doc


@pytest.mark.asyncio
async def test_create_comment(client: AsyncClient, db_session: AsyncSession):
    user, token = await _create_user_with_roles(db_session, ["editor"])
    doc = await _create_document(db_session)

    response = await client.post(
        f"/api/documents/{doc.id}/comments",
        json={"content": "This is a test comment"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["content"] == "This is a test comment"
    assert data["document_id"] == doc.id
    assert data["user_id"] == user.id
    assert data["username"] == "testuser"
    assert data["parent_id"] is None


@pytest.mark.asyncio
async def test_list_comments(client: AsyncClient, db_session: AsyncSession):
    user, token = await _create_user_with_roles(db_session, ["editor"])
    doc = await _create_document(db_session)

    await client.post(
        f"/api/documents/{doc.id}/comments",
        json={"content": "First comment"},
        headers={"Authorization": f"Bearer {token}"},
    )
    await client.post(
        f"/api/documents/{doc.id}/comments",
        json={"content": "Second comment"},
        headers={"Authorization": f"Bearer {token}"},
    )

    response = await client.get(f"/api/documents/{doc.id}/comments")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["content"] == "First comment"
    assert data[1]["content"] == "Second comment"


@pytest.mark.asyncio
async def test_reply_comment(client: AsyncClient, db_session: AsyncSession):
    user, token = await _create_user_with_roles(db_session, ["editor"])
    doc = await _create_document(db_session)

    # Create parent comment
    parent_resp = await client.post(
        f"/api/documents/{doc.id}/comments",
        json={"content": "Parent comment"},
        headers={"Authorization": f"Bearer {token}"},
    )
    parent_id = parent_resp.json()["id"]

    # Create reply
    reply_resp = await client.post(
        f"/api/documents/{doc.id}/comments",
        json={"content": "Reply to parent", "parent_id": parent_id},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert reply_resp.status_code == 201
    data = reply_resp.json()
    assert data["parent_id"] == parent_id
    assert data["content"] == "Reply to parent"


@pytest.mark.asyncio
async def test_update_comment(client: AsyncClient, db_session: AsyncSession):
    user, token = await _create_user_with_roles(db_session, ["editor"])
    doc = await _create_document(db_session)

    create_resp = await client.post(
        f"/api/documents/{doc.id}/comments",
        json={"content": "Original content"},
        headers={"Authorization": f"Bearer {token}"},
    )
    comment_id = create_resp.json()["id"]

    response = await client.put(
        f"/api/comments/{comment_id}",
        json={"content": "Updated content"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["content"] == "Updated content"
    assert data["updated_at"] is not None


@pytest.mark.asyncio
async def test_delete_comment(client: AsyncClient, db_session: AsyncSession):
    user, token = await _create_user_with_roles(db_session, ["editor"])
    doc = await _create_document(db_session)

    create_resp = await client.post(
        f"/api/documents/{doc.id}/comments",
        json={"content": "To be deleted"},
        headers={"Authorization": f"Bearer {token}"},
    )
    comment_id = create_resp.json()["id"]

    response = await client.delete(
        f"/api/comments/{comment_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 204

    # Verify deleted
    list_resp = await client.get(f"/api/documents/{doc.id}/comments")
    assert len(list_resp.json()) == 0


@pytest.mark.asyncio
async def test_mention_creates_notification(client: AsyncClient, db_session: AsyncSession):
    # Create the user who will be mentioned
    mentioned_user, _ = await _create_user_with_roles(db_session, ["editor"], username="johndoe")

    # Create the commenting user
    commenter, token = await _create_user_with_roles(db_session, ["editor"], username="commenter")
    doc = await _create_document(db_session)

    response = await client.post(
        f"/api/documents/{doc.id}/comments",
        json={"content": "Hey @johndoe check this out!"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201

    # Verify notification was created for the mentioned user
    result = await db_session.execute(
        select(Notification).where(Notification.user_id == mentioned_user.id)
    )
    notifications = list(result.scalars().all())
    assert len(notifications) == 1
    assert notifications[0].notification_type == "mention"
    assert "mentioned you" in notifications[0].message


@pytest.mark.asyncio
async def test_unauthenticated_create_fails(client: AsyncClient, db_session: AsyncSession):
    doc = await _create_document(db_session)

    response = await client.post(
        f"/api/documents/{doc.id}/comments",
        json={"content": "Should fail"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_admin_can_delete_others_comment(client: AsyncClient, db_session: AsyncSession):
    # Create regular user who makes the comment
    user, user_token = await _create_user_with_roles(db_session, ["editor"], username="regular")
    doc = await _create_document(db_session)

    create_resp = await client.post(
        f"/api/documents/{doc.id}/comments",
        json={"content": "Regular user comment"},
        headers={"Authorization": f"Bearer {user_token}"},
    )
    comment_id = create_resp.json()["id"]

    # Create admin user
    admin, admin_token = await _create_user_with_roles(db_session, ["admin"], username="adminuser")

    # Admin deletes the comment
    response = await client.delete(
        f"/api/comments/{comment_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 204
