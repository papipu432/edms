from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password
from app.models.document import Document, DocumentStatus
from app.models.group import Group
from app.models.sla import DocumentSLA, SLAPolicy, SLAStatus
from app.models.user import Role, User, UserRole


async def _create_user(
    db: AsyncSession, username: str = "slauser", roles: list[str] | None = None
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


async def _create_document(db: AsyncSession, group: Group | None = None) -> Document:
    """Helper to create a group and document."""
    if group is None:
        group = Group(name="SLA Test Group")
        db.add(group)
        await db.flush()
        await db.refresh(group)
    doc = Document(
        group_id=group.id,
        original_filename="sla_test.pdf",
        storage_path="/tmp/sla_test.pdf",
        file_type="application/pdf",
        file_size=2048,
        status=DocumentStatus.uploaded,
    )
    db.add(doc)
    await db.flush()
    await db.refresh(doc)
    return doc


@pytest.mark.asyncio
async def test_create_sla_policy(client: AsyncClient, db_session: AsyncSession):
    user, token = await _create_user(db_session, "slaadmin", ["admin"])

    group = Group(name="Policy Group")
    db_session.add(group)
    await db_session.flush()
    await db_session.refresh(group)

    response = await client.post(
        "/api/sla-policies",
        json={
            "folder_id": group.id,
            "action": "approval",
            "max_duration_hours": 48,
            "escalation_role": "admin",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["folder_id"] == group.id
    assert data["max_duration_hours"] == 48
    assert data["escalation_role"] == "admin"
    assert data["is_active"] is True


@pytest.mark.asyncio
async def test_list_sla_policies(client: AsyncClient, db_session: AsyncSession):
    user, token = await _create_user(db_session, "slaadmin2", ["admin"])

    group = Group(name="Policy Group 2")
    db_session.add(group)
    await db_session.flush()
    await db_session.refresh(group)

    await client.post(
        "/api/sla-policies",
        json={"folder_id": group.id, "action": "approval", "max_duration_hours": 24},
        headers={"Authorization": f"Bearer {token}"},
    )

    response = await client.get("/api/sla-policies")
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1


@pytest.mark.asyncio
async def test_start_sla_for_document(client: AsyncClient, db_session: AsyncSession):
    user, token = await _create_user(db_session, "slaadmin3", ["admin"])

    group = Group(name="SLA Start Group")
    db_session.add(group)
    await db_session.flush()
    await db_session.refresh(group)

    # Create policy
    await client.post(
        "/api/sla-policies",
        json={"folder_id": group.id, "action": "approval", "max_duration_hours": 72},
        headers={"Authorization": f"Bearer {token}"},
    )

    # Create document in that folder
    doc = await _create_document(db_session, group)

    # Start SLA
    response = await client.post(
        f"/api/documents/{doc.id}/sla/start",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["document_id"] == doc.id
    assert data["status"] == "on_time"
    assert data["percent_elapsed"] >= 0
    assert data["deadline_at"] is not None


@pytest.mark.asyncio
async def test_get_document_sla_status(client: AsyncClient, db_session: AsyncSession):
    user, token = await _create_user(db_session, "slaadmin4", ["admin"])

    group = Group(name="SLA Status Group")
    db_session.add(group)
    await db_session.flush()
    await db_session.refresh(group)

    await client.post(
        "/api/sla-policies",
        json={"folder_id": group.id, "action": "approval", "max_duration_hours": 24},
        headers={"Authorization": f"Bearer {token}"},
    )

    doc = await _create_document(db_session, group)
    await client.post(
        f"/api/documents/{doc.id}/sla/start",
        headers={"Authorization": f"Bearer {token}"},
    )

    response = await client.get(
        f"/api/documents/{doc.id}/sla",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "on_time"


@pytest.mark.asyncio
async def test_check_breaches_updates_status(client: AsyncClient, db_session: AsyncSession):
    user, token = await _create_user(db_session, "slaadmin5", ["admin"])

    group = Group(name="SLA Breach Group")
    db_session.add(group)
    await db_session.flush()
    await db_session.refresh(group)

    # Create policy
    policy = SLAPolicy(
        folder_id=group.id,
        action="approval",
        max_duration_hours=1,
        escalation_role="admin",
        is_active=True,
    )
    db_session.add(policy)
    await db_session.flush()
    await db_session.refresh(policy)

    doc = await _create_document(db_session, group)

    # Create a DocumentSLA that's already past deadline (started 2 hours ago, 1 hour deadline)
    now = datetime.now(timezone.utc)
    sla = DocumentSLA(
        document_id=doc.id,
        policy_id=policy.id,
        started_at=now - timedelta(hours=2),
        deadline_at=now - timedelta(hours=1),
        status=SLAStatus.on_time,
    )
    db_session.add(sla)
    await db_session.flush()

    # Run check-breaches
    response = await client.put(
        "/api/sla/check-breaches",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["breached"] >= 1


@pytest.mark.asyncio
async def test_sla_dashboard(client: AsyncClient, db_session: AsyncSession):
    user, token = await _create_user(db_session, "slaadmin6", ["admin"])

    group = Group(name="SLA Dashboard Group")
    db_session.add(group)
    await db_session.flush()
    await db_session.refresh(group)

    policy = SLAPolicy(
        folder_id=group.id,
        action="approval",
        max_duration_hours=24,
        is_active=True,
    )
    db_session.add(policy)
    await db_session.flush()
    await db_session.refresh(policy)

    doc = await _create_document(db_session, group)

    now = datetime.now(timezone.utc)
    sla = DocumentSLA(
        document_id=doc.id,
        policy_id=policy.id,
        started_at=now,
        deadline_at=now + timedelta(hours=24),
        status=SLAStatus.on_time,
    )
    db_session.add(sla)
    await db_session.flush()

    response = await client.get(
        "/api/sla/dashboard",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    assert "on_time" in data
    assert "at_risk" in data
    assert "breached" in data
    assert "completed" in data
    assert "compliance_rate" in data
    assert data["compliance_rate"] >= 0


@pytest.mark.asyncio
async def test_delete_sla_policy(client: AsyncClient, db_session: AsyncSession):
    user, token = await _create_user(db_session, "slaadmin7", ["admin"])

    group = Group(name="Delete Policy Group")
    db_session.add(group)
    await db_session.flush()
    await db_session.refresh(group)

    create_resp = await client.post(
        "/api/sla-policies",
        json={"folder_id": group.id, "action": "approval", "max_duration_hours": 12},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert create_resp.status_code == 201
    policy_id = create_resp.json()["id"]

    response = await client.delete(
        f"/api/sla-policies/{policy_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 204
