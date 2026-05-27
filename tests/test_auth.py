import pytest
import pytest_asyncio
from httpx import AsyncClient

from app.core.security import create_access_token, hash_password
from app.models.user import Role, RoleName, User


@pytest_asyncio.fixture
async def seeded_db(db_session):
    """Seed roles into the test database."""
    for role_name in RoleName:
        db_session.add(Role(name=role_name, description=f"{role_name.value} role"))
    await db_session.flush()
    return db_session


@pytest_asyncio.fixture
async def admin_user(seeded_db):
    """Create an admin user in the test database."""
    from sqlalchemy import select

    result = await seeded_db.execute(select(Role).where(Role.name == RoleName.admin))
    admin_role = result.scalar_one()

    user = User(
        username="admin",
        email="admin@edms.local",
        hashed_password=hash_password("admin"),
    )
    user.roles.append(admin_role)
    seeded_db.add(user)
    await seeded_db.flush()
    await seeded_db.refresh(user)
    return user


@pytest_asyncio.fixture
async def admin_token(admin_user):
    """Create a valid JWT token for the admin user."""
    return create_access_token(data={"sub": admin_user.username})


@pytest_asyncio.fixture
async def regular_user(seeded_db):
    """Create a regular user (no roles) in the test database."""
    user = User(
        username="regular",
        email="regular@edms.local",
        hashed_password=hash_password("password123"),
    )
    seeded_db.add(user)
    await seeded_db.flush()
    await seeded_db.refresh(user)
    return user


@pytest_asyncio.fixture
async def regular_token(regular_user):
    """Create a valid JWT token for the regular user."""
    return create_access_token(data={"sub": regular_user.username})


@pytest.mark.asyncio
async def test_register_creates_user(client: AsyncClient, seeded_db):
    response = await client.post(
        "/api/auth/register",
        json={
            "username": "newuser",
            "email": "newuser@example.com",
            "password": "strongpass123",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["username"] == "newuser"
    assert data["email"] == "newuser@example.com"
    assert data["is_active"] is True
    assert data["roles"] == []


@pytest.mark.asyncio
async def test_register_duplicate_username(client: AsyncClient, admin_user):
    response = await client.post(
        "/api/auth/register",
        json={
            "username": "admin",
            "email": "other@example.com",
            "password": "pass123",
        },
    )
    assert response.status_code == 409
    assert "already registered" in response.json()["detail"]


@pytest.mark.asyncio
async def test_login_valid_credentials(client: AsyncClient, admin_user):
    response = await client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "admin"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_login_invalid_credentials(client: AsyncClient, admin_user):
    response = await client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "wrongpassword"},
    )
    assert response.status_code == 401
    assert "Invalid credentials" in response.json()["detail"]


@pytest.mark.asyncio
async def test_get_me_with_valid_token(client: AsyncClient, admin_user, admin_token):
    response = await client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["username"] == "admin"
    assert "admin" in data["roles"]


@pytest.mark.asyncio
async def test_get_me_without_token(client: AsyncClient, seeded_db):
    response = await client.get("/api/auth/me")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_role_protected_endpoint_blocks_non_admin(
    client: AsyncClient, regular_user, regular_token
):
    """Non-admin user cannot access admin-only endpoints."""
    response = await client.get(
        "/api/users",
        headers={"Authorization": f"Bearer {regular_token}"},
    )
    assert response.status_code == 403
    assert "Insufficient permissions" in response.json()["detail"]


@pytest.mark.asyncio
async def test_role_protected_endpoint_allows_admin(
    client: AsyncClient, admin_user, admin_token
):
    """Admin user can access admin-only endpoints."""
    response = await client.get(
        "/api/users",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1
    assert any(u["username"] == "admin" for u in data)
