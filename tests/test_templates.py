import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password
from app.models.group import Group
from app.models.user import User


async def _create_user_and_token(
    db: AsyncSession, username: str = "tmpluser"
) -> tuple[User, str]:
    user = User(
        username=username,
        email=f"{username}@example.com",
        display_name="Template Test User",
        hashed_password=hash_password("password123"),
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    token = create_access_token(data={"sub": user.username})
    return user, token


async def _create_group(db: AsyncSession) -> Group:
    group = Group(name="Template Group")
    db.add(group)
    await db.flush()
    await db.refresh(group)
    return group


@pytest.mark.asyncio
async def test_create_template(client: AsyncClient, db_session: AsyncSession):
    """Test creating a document template."""
    _, token = await _create_user_and_token(db_session)

    response = await client.post(
        "/api/templates",
        json={
            "name": "Invoice Template",
            "description": "Standard invoice format",
            "required_fields": {"vendor": "string", "amount": "number", "date": "date"},
            "default_lifecycle_type": "expiring",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Invoice Template"
    assert data["description"] == "Standard invoice format"
    assert data["required_fields"] == {"vendor": "string", "amount": "number", "date": "date"}
    assert data["default_lifecycle_type"] == "expiring"
    assert "id" in data


@pytest.mark.asyncio
async def test_list_templates(client: AsyncClient, db_session: AsyncSession):
    """Test listing all templates."""
    _, token = await _create_user_and_token(db_session, username="tmpllist")

    await client.post(
        "/api/templates",
        json={"name": "Template A", "required_fields": {"field1": "string"}},
        headers={"Authorization": f"Bearer {token}"},
    )
    await client.post(
        "/api/templates",
        json={"name": "Template B", "required_fields": {"field2": "string"}},
        headers={"Authorization": f"Bearer {token}"},
    )

    response = await client.get(
        "/api/templates",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 2
    names = [t["name"] for t in data]
    assert "Template A" in names
    assert "Template B" in names


@pytest.mark.asyncio
async def test_get_template_by_id(client: AsyncClient, db_session: AsyncSession):
    """Test getting a template by ID."""
    _, token = await _create_user_and_token(db_session, username="tmplget")

    create_resp = await client.post(
        "/api/templates",
        json={"name": "Fetch Me", "required_fields": {"x": "string"}},
        headers={"Authorization": f"Bearer {token}"},
    )
    template_id = create_resp.json()["id"]

    response = await client.get(
        f"/api/templates/{template_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Fetch Me"


@pytest.mark.asyncio
async def test_update_template(client: AsyncClient, db_session: AsyncSession):
    """Test updating a template."""
    _, token = await _create_user_and_token(db_session, username="tmplupd")

    create_resp = await client.post(
        "/api/templates",
        json={"name": "Old Name", "required_fields": {"a": "string"}},
        headers={"Authorization": f"Bearer {token}"},
    )
    template_id = create_resp.json()["id"]

    response = await client.put(
        f"/api/templates/{template_id}",
        json={"name": "New Name", "required_fields": {"a": "string", "b": "number"}},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "New Name"
    assert data["required_fields"] == {"a": "string", "b": "number"}


@pytest.mark.asyncio
async def test_delete_template(client: AsyncClient, db_session: AsyncSession):
    """Test deleting a template."""
    _, token = await _create_user_and_token(db_session, username="tmpldel")

    create_resp = await client.post(
        "/api/templates",
        json={"name": "Delete Me", "required_fields": {}},
        headers={"Authorization": f"Bearer {token}"},
    )
    template_id = create_resp.json()["id"]

    response = await client.delete(
        f"/api/templates/{template_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 204

    # Verify it's gone
    get_resp = await client.get(
        f"/api/templates/{template_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_create_document_from_template(
    client: AsyncClient, db_session: AsyncSession
):
    """Test creating a document from a template."""
    _, token = await _create_user_and_token(db_session, username="tmpldoc")
    group = await _create_group(db_session)

    create_resp = await client.post(
        "/api/templates",
        json={
            "name": "Contract Template",
            "required_fields": {"party_a": "string", "party_b": "string"},
            "default_folder_id": group.id,
            "default_lifecycle_type": "permanent",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    template_id = create_resp.json()["id"]

    response = await client.post(
        f"/api/templates/{template_id}/create-document",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["template_id"] == template_id
    assert data["template_name"] == "Contract Template"
    assert data["required_fields"] == {"party_a": "string", "party_b": "string"}
    assert data["default_folder_id"] == group.id
    assert data["default_lifecycle_type"] == "permanent"


@pytest.mark.asyncio
async def test_template_not_found(client: AsyncClient, db_session: AsyncSession):
    """Test getting a non-existent template returns 404."""
    _, token = await _create_user_and_token(db_session, username="tmplnf")

    response = await client.get(
        "/api/templates/99999",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404
