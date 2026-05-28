import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password
from app.models.document import Document, DocumentStatus
from app.models.document_lock import DocumentLock
from app.models.group import Group
from app.models.user import Role, User, UserRole

from datetime import datetime, timedelta


async def _create_user_with_roles(
    db: AsyncSession, roles: list[str] | None = None, username: str = "testuser"
) -> tuple[User, str]:
    """Helper to create a user with specified roles and return (user, token)."""
    if roles:
        for role_code in roles:
            existing = await db.execute(select(Role).where(Role.code == role_code))
            if existing.scalar_one_or_none() is None:
                db.add(Role(
                    code=role_code, name=role_code.title(),
                    description=f"{role_code} role", is_system=True,
                ))
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
async def test_lock_document(client: AsyncClient, db_session: AsyncSession):
    user, token = await _create_user_with_roles(db_session, ["editor"])
    doc = await _create_document(db_session)

    response = await client.post(
        f"/api/documents/{doc.id}/lock",
        json={"reason": "Editing", "duration_hours": 2},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["document_id"] == doc.id
    assert data["user_id"] == user.id
    assert data["username"] == "testuser"
    assert data["reason"] == "Editing"
    assert data["is_expired"] is False


@pytest.mark.asyncio
async def test_lock_status_shows_locked(client: AsyncClient, db_session: AsyncSession):
    user, token = await _create_user_with_roles(db_session, ["editor"])
    doc = await _create_document(db_session)

    await client.post(
        f"/api/documents/{doc.id}/lock",
        json={"duration_hours": 24},
        headers={"Authorization": f"Bearer {token}"},
    )

    response = await client.get(f"/api/documents/{doc.id}/lock")
    assert response.status_code == 200
    data = response.json()
    assert data["is_locked"] is True
    assert data["lock"]["document_id"] == doc.id


@pytest.mark.asyncio
async def test_unlock_document(client: AsyncClient, db_session: AsyncSession):
    user, token = await _create_user_with_roles(db_session, ["editor"])
    doc = await _create_document(db_session)

    await client.post(
        f"/api/documents/{doc.id}/lock",
        json={"duration_hours": 24},
        headers={"Authorization": f"Bearer {token}"},
    )

    response = await client.delete(
        f"/api/documents/{doc.id}/lock",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 204

    # Verify unlocked
    status_resp = await client.get(f"/api/documents/{doc.id}/lock")
    assert status_resp.json()["is_locked"] is False


@pytest.mark.asyncio
async def test_cannot_lock_already_locked(client: AsyncClient, db_session: AsyncSession):
    user1, token1 = await _create_user_with_roles(db_session, ["editor"], username="user1")
    user2, token2 = await _create_user_with_roles(db_session, ["editor"], username="user2")
    doc = await _create_document(db_session)

    # User 1 locks
    await client.post(
        f"/api/documents/{doc.id}/lock",
        json={"duration_hours": 24},
        headers={"Authorization": f"Bearer {token1}"},
    )

    # User 2 tries to lock
    response = await client.post(
        f"/api/documents/{doc.id}/lock",
        json={"duration_hours": 24},
        headers={"Authorization": f"Bearer {token2}"},
    )
    assert response.status_code == 409
    assert "already locked" in response.json()["detail"]


@pytest.mark.asyncio
async def test_admin_force_unlock(client: AsyncClient, db_session: AsyncSession):
    user, user_token = await _create_user_with_roles(
        db_session, ["editor"], username="regular"
    )
    admin, admin_token = await _create_user_with_roles(
        db_session, ["admin"], username="adminuser"
    )
    doc = await _create_document(db_session)

    # Regular user locks
    await client.post(
        f"/api/documents/{doc.id}/lock",
        json={"duration_hours": 24},
        headers={"Authorization": f"Bearer {user_token}"},
    )

    # Admin force-unlocks
    response = await client.delete(
        f"/api/documents/{doc.id}/lock",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 204

    # Verify unlocked
    status_resp = await client.get(f"/api/documents/{doc.id}/lock")
    assert status_resp.json()["is_locked"] is False


@pytest.mark.asyncio
async def test_expired_lock_allows_relock(client: AsyncClient, db_session: AsyncSession):
    user1, token1 = await _create_user_with_roles(db_session, ["editor"], username="user1")
    user2, token2 = await _create_user_with_roles(db_session, ["editor"], username="user2")
    doc = await _create_document(db_session)

    # Create an already-expired lock directly in the database
    expired_lock = DocumentLock(
        document_id=doc.id,
        user_id=user1.id,
        locked_at=datetime.utcnow() - timedelta(hours=48),
        expires_at=datetime.utcnow() - timedelta(hours=1),
        reason="Old lock",
    )
    db_session.add(expired_lock)
    await db_session.flush()

    # User 2 should be able to lock since the existing lock is expired
    response = await client.post(
        f"/api/documents/{doc.id}/lock",
        json={"duration_hours": 24},
        headers={"Authorization": f"Bearer {token2}"},
    )
    assert response.status_code == 201
    assert response.json()["user_id"] == user2.id


@pytest.mark.asyncio
async def test_lock_not_found_on_unlock(client: AsyncClient, db_session: AsyncSession):
    user, token = await _create_user_with_roles(db_session, ["editor"])
    doc = await _create_document(db_session)

    response = await client.delete(
        f"/api/documents/{doc.id}/lock",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404
