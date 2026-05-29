"""Tests for multi-tenant support."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password
from app.models.document import Document, DocumentStatus
from app.models.group import Group
from app.models.tenant import Tenant
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
async def test_create_tenant(client: AsyncClient, db_session: AsyncSession):
    """Test creating a tenant."""
    _, token = await _create_admin_user(db_session)

    response = await client.post(
        "/api/tenants",
        json={"name": "Acme Corp", "slug": "acme"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Acme Corp"
    assert data["slug"] == "acme"
    assert data["is_active"] is True


@pytest.mark.asyncio
async def test_list_tenants(client: AsyncClient, db_session: AsyncSession):
    """Test listing tenants."""
    _, token = await _create_admin_user(db_session)

    tenant = Tenant(name="Test Tenant", slug="test-tenant")
    db_session.add(tenant)
    await db_session.flush()

    response = await client.get(
        "/api/tenants",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1


@pytest.mark.asyncio
async def test_get_tenant(client: AsyncClient, db_session: AsyncSession):
    """Test getting a single tenant."""
    _, token = await _create_admin_user(db_session)

    tenant = Tenant(name="Get Tenant", slug="get-tenant")
    db_session.add(tenant)
    await db_session.flush()
    await db_session.refresh(tenant)

    response = await client.get(
        f"/api/tenants/{tenant.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Get Tenant"


@pytest.mark.asyncio
async def test_update_tenant(client: AsyncClient, db_session: AsyncSession):
    """Test updating a tenant."""
    _, token = await _create_admin_user(db_session)

    tenant = Tenant(name="Old Name", slug="old-slug")
    db_session.add(tenant)
    await db_session.flush()
    await db_session.refresh(tenant)

    response = await client.put(
        f"/api/tenants/{tenant.id}",
        json={"name": "New Name"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "New Name"


@pytest.mark.asyncio
async def test_delete_tenant(client: AsyncClient, db_session: AsyncSession):
    """Test deleting a tenant."""
    _, token = await _create_admin_user(db_session)

    tenant = Tenant(name="Delete Me", slug="delete-me")
    db_session.add(tenant)
    await db_session.flush()
    await db_session.refresh(tenant)

    response = await client.delete(
        f"/api/tenants/{tenant.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 204


@pytest.mark.asyncio
async def test_duplicate_slug_rejected(client: AsyncClient, db_session: AsyncSession):
    """Test that duplicate tenant slugs are rejected."""
    _, token = await _create_admin_user(db_session)

    tenant = Tenant(name="First", slug="unique-slug")
    db_session.add(tenant)
    await db_session.flush()

    response = await client.post(
        "/api/tenants",
        json={"name": "Second", "slug": "unique-slug"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_tenant_id_on_document(db_session: AsyncSession):
    """Test that Document model has nullable tenant_id column."""
    tenant = Tenant(name="Doc Tenant", slug="doc-tenant")
    db_session.add(tenant)
    await db_session.flush()
    await db_session.refresh(tenant)

    group = Group(name="TenantGroup")
    db_session.add(group)
    await db_session.flush()
    await db_session.refresh(group)

    doc = Document(
        group_id=group.id,
        original_filename="tenant_doc.pdf",
        storage_path="/tmp/tenant_doc.pdf",
        file_type="application/pdf",
        file_size=1024,
        status=DocumentStatus.uploaded,
        tenant_id=tenant.id,
    )
    db_session.add(doc)
    await db_session.flush()
    await db_session.refresh(doc)

    assert doc.tenant_id == tenant.id


@pytest.mark.asyncio
async def test_tenant_id_on_group(db_session: AsyncSession):
    """Test that Group model has nullable tenant_id column."""
    tenant = Tenant(name="Group Tenant", slug="group-tenant")
    db_session.add(tenant)
    await db_session.flush()
    await db_session.refresh(tenant)

    group = Group(name="Tenant Group", tenant_id=tenant.id)
    db_session.add(group)
    await db_session.flush()
    await db_session.refresh(group)

    assert group.tenant_id == tenant.id


@pytest.mark.asyncio
async def test_tenant_id_on_user(db_session: AsyncSession):
    """Test that User model has nullable tenant_id column."""
    tenant = Tenant(name="User Tenant", slug="user-tenant")
    db_session.add(tenant)
    await db_session.flush()
    await db_session.refresh(tenant)

    user = User(
        username="tenant_user",
        email="tenant_user@example.com",
        display_name="Tenant User",
        hashed_password=hash_password("password123"),
        tenant_id=tenant.id,
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)

    assert user.tenant_id == tenant.id


@pytest.mark.asyncio
async def test_tenant_id_nullable(db_session: AsyncSession):
    """Test that tenant_id is nullable (backward compat)."""
    group = Group(name="No Tenant Group")
    db_session.add(group)
    await db_session.flush()
    await db_session.refresh(group)

    assert group.tenant_id is None
