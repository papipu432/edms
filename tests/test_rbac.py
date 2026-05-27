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
async def test_admin_can_list_users(client: AsyncClient, admin_user, admin_token):
    response = await client.get(
        "/api/users",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1


@pytest.mark.asyncio
async def test_non_admin_cannot_list_users(
    client: AsyncClient, regular_user, regular_token
):
    response = await client.get(
        "/api/users",
        headers={"Authorization": f"Bearer {regular_token}"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_admin_can_assign_role(
    client: AsyncClient, admin_user, admin_token, regular_user
):
    response = await client.post(
        f"/api/users/{regular_user.id}/roles",
        json={"role_name": "editor"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "editor" in data["roles"]


@pytest.mark.asyncio
async def test_admin_can_remove_role(
    client: AsyncClient, admin_user, admin_token, regular_user
):
    # First assign a role
    await client.post(
        f"/api/users/{regular_user.id}/roles",
        json={"role_name": "reviewer"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    # Then remove it
    response = await client.delete(
        f"/api/users/{regular_user.id}/roles/reviewer",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "reviewer" not in data["roles"]


@pytest.mark.asyncio
async def test_admin_can_create_folder_assignment(
    client: AsyncClient, admin_user, admin_token, regular_user
):
    response = await client.post(
        f"/api/users/{regular_user.id}/folders",
        json={"folder_path": "/group_1", "role_name": "editor"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["folder_path"] == "/group_1"
    assert data["role_name"] == "editor"
    assert data["user_id"] == regular_user.id


@pytest.mark.asyncio
async def test_admin_can_list_folder_assignments(
    client: AsyncClient, admin_user, admin_token, regular_user
):
    # Create a folder assignment first
    await client.post(
        f"/api/users/{regular_user.id}/folders",
        json={"folder_path": "/docs", "role_name": "reviewer"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    response = await client.get(
        f"/api/users/{regular_user.id}/folders",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    assert any(a["folder_path"] == "/docs" for a in data)


@pytest.mark.asyncio
async def test_admin_can_delete_folder_assignment(
    client: AsyncClient, admin_user, admin_token, regular_user
):
    # Create a folder assignment first
    create_resp = await client.post(
        f"/api/users/{regular_user.id}/folders",
        json={"folder_path": "/temp", "role_name": "annotator"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assignment_id = create_resp.json()["id"]

    # Delete it
    response = await client.delete(
        f"/api/users/{regular_user.id}/folders/{assignment_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 204

    # Verify it's gone
    list_resp = await client.get(
        f"/api/users/{regular_user.id}/folders",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assignments = list_resp.json()
    assert not any(a["id"] == assignment_id for a in assignments)
