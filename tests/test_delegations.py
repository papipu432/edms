from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password
from app.models.user import Role, User, UserRole


async def _create_user(
    db: AsyncSession, username: str = "delegator", roles: list[str] | None = None
) -> tuple[User, str]:
    """Helper to create a user and return (user, token)."""
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
            db.add(UserRole(user_id=user.id, role_id=role.id))
        await db.flush()
        await db.refresh(user)

    token = create_access_token(data={"sub": user.username})
    return user, token


@pytest.mark.asyncio
async def test_create_delegation(client: AsyncClient, db_session: AsyncSession):
    delegator, delegator_token = await _create_user(db_session, "delegator1")
    delegate, _ = await _create_user(db_session, "delegate1")

    now = datetime.now(timezone.utc)
    response = await client.post(
        "/api/delegations",
        json={
            "delegate_id": delegate.id,
            "start_date": now.isoformat(),
            "end_date": (now + timedelta(days=7)).isoformat(),
            "scope_type": "all",
        },
        headers={"Authorization": f"Bearer {delegator_token}"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["delegator_id"] == delegator.id
    assert data["delegate_id"] == delegate.id
    assert data["delegator_username"] == "delegator1"
    assert data["delegate_username"] == "delegate1"
    assert data["scope_type"] == "all"
    assert data["is_active"] is True


@pytest.mark.asyncio
async def test_list_delegations(client: AsyncClient, db_session: AsyncSession):
    delegator, delegator_token = await _create_user(db_session, "delegator2")
    delegate, delegate_token = await _create_user(db_session, "delegate2")

    now = datetime.now(timezone.utc)
    await client.post(
        "/api/delegations",
        json={
            "delegate_id": delegate.id,
            "start_date": (now - timedelta(hours=1)).isoformat(),
            "end_date": (now + timedelta(days=7)).isoformat(),
            "scope_type": "all",
        },
        headers={"Authorization": f"Bearer {delegator_token}"},
    )

    # Delegator should see it
    response = await client.get(
        "/api/delegations",
        headers={"Authorization": f"Bearer {delegator_token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1

    # Delegate should also see it
    response = await client.get(
        "/api/delegations",
        headers={"Authorization": f"Bearer {delegate_token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1


@pytest.mark.asyncio
async def test_revoke_delegation(client: AsyncClient, db_session: AsyncSession):
    delegator, delegator_token = await _create_user(db_session, "delegator3")
    delegate, _ = await _create_user(db_session, "delegate3")

    now = datetime.now(timezone.utc)
    create_resp = await client.post(
        "/api/delegations",
        json={
            "delegate_id": delegate.id,
            "start_date": (now - timedelta(hours=1)).isoformat(),
            "end_date": (now + timedelta(days=7)).isoformat(),
            "scope_type": "all",
        },
        headers={"Authorization": f"Bearer {delegator_token}"},
    )
    assert create_resp.status_code == 201
    delegation_id = create_resp.json()["id"]

    # Revoke
    response = await client.delete(
        f"/api/delegations/{delegation_id}",
        headers={"Authorization": f"Bearer {delegator_token}"},
    )
    assert response.status_code == 204

    # Should no longer appear in active list
    list_resp = await client.get(
        "/api/delegations",
        headers={"Authorization": f"Bearer {delegator_token}"},
    )
    assert list_resp.status_code == 200
    data = list_resp.json()
    active_ids = [d["id"] for d in data]
    assert delegation_id not in active_ids


@pytest.mark.asyncio
async def test_expired_delegation_not_returned(client: AsyncClient, db_session: AsyncSession):
    delegator, delegator_token = await _create_user(db_session, "delegator4")
    delegate, _ = await _create_user(db_session, "delegate4")

    # Create an already-expired delegation
    now = datetime.now(timezone.utc)
    response = await client.post(
        "/api/delegations",
        json={
            "delegate_id": delegate.id,
            "start_date": (now - timedelta(days=10)).isoformat(),
            "end_date": (now - timedelta(days=1)).isoformat(),
            "scope_type": "all",
        },
        headers={"Authorization": f"Bearer {delegator_token}"},
    )
    assert response.status_code == 201

    # Should not appear in active list
    list_resp = await client.get(
        "/api/delegations",
        headers={"Authorization": f"Bearer {delegator_token}"},
    )
    assert list_resp.status_code == 200
    data = list_resp.json()
    assert len(data) == 0


@pytest.mark.asyncio
async def test_delegation_with_folder_scope(client: AsyncClient, db_session: AsyncSession):
    from app.models.group import Group

    delegator, delegator_token = await _create_user(db_session, "delegator5")
    delegate, _ = await _create_user(db_session, "delegate5")

    group = Group(name="Scoped Folder")
    db_session.add(group)
    await db_session.flush()
    await db_session.refresh(group)

    now = datetime.now(timezone.utc)
    response = await client.post(
        "/api/delegations",
        json={
            "delegate_id": delegate.id,
            "start_date": now.isoformat(),
            "end_date": (now + timedelta(days=7)).isoformat(),
            "scope_type": "folder",
            "scope_folder_id": group.id,
        },
        headers={"Authorization": f"Bearer {delegator_token}"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["scope_type"] == "folder"
    assert data["scope_folder_id"] == group.id
