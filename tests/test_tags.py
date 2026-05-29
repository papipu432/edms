import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password
from app.models.document import Document, DocumentStatus
from app.models.group import Group
from app.models.user import User


async def _create_user_and_token(
    db: AsyncSession, username: str = "taguser"
) -> tuple[User, str]:
    user = User(
        username=username,
        email=f"{username}@example.com",
        display_name="Tag Test User",
        hashed_password=hash_password("password123"),
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    token = create_access_token(data={"sub": user.username})
    return user, token


async def _create_document(db: AsyncSession) -> Document:
    group = Group(name="Tag Test Group")
    db.add(group)
    await db.flush()
    await db.refresh(group)
    doc = Document(
        group_id=group.id,
        original_filename="tag_test.pdf",
        storage_path="/tmp/tag_test.pdf",
        file_type="application/pdf",
        file_size=1024,
        status=DocumentStatus.uploaded,
    )
    db.add(doc)
    await db.flush()
    await db.refresh(doc)
    return doc


@pytest.mark.asyncio
async def test_create_tag(client: AsyncClient, db_session: AsyncSession):
    """Test creating a tag."""
    _, token = await _create_user_and_token(db_session)

    response = await client.post(
        "/api/tags",
        json={"name": "urgent", "color": "#ff0000"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "urgent"
    assert data["color"] == "#ff0000"
    assert "id" in data


@pytest.mark.asyncio
async def test_list_tags(client: AsyncClient, db_session: AsyncSession):
    """Test listing all tags."""
    _, token = await _create_user_and_token(db_session, username="taglist")

    # Create two tags
    await client.post(
        "/api/tags",
        json={"name": "alpha"},
        headers={"Authorization": f"Bearer {token}"},
    )
    await client.post(
        "/api/tags",
        json={"name": "beta"},
        headers={"Authorization": f"Bearer {token}"},
    )

    response = await client.get(
        "/api/tags",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 2
    names = [t["name"] for t in data]
    assert "alpha" in names
    assert "beta" in names


@pytest.mark.asyncio
async def test_delete_tag(client: AsyncClient, db_session: AsyncSession):
    """Test deleting a tag."""
    _, token = await _create_user_and_token(db_session, username="tagdel")

    create_resp = await client.post(
        "/api/tags",
        json={"name": "to_delete"},
        headers={"Authorization": f"Bearer {token}"},
    )
    tag_id = create_resp.json()["id"]

    response = await client.delete(
        f"/api/tags/{tag_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 204


@pytest.mark.asyncio
async def test_delete_tag_not_found(client: AsyncClient, db_session: AsyncSession):
    """Test deleting a non-existent tag returns 404."""
    _, token = await _create_user_and_token(db_session, username="tagdelnf")

    response = await client.delete(
        "/api/tags/99999",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_add_tag_to_document(client: AsyncClient, db_session: AsyncSession):
    """Test adding a tag to a document."""
    _, token = await _create_user_and_token(db_session, username="tagdoc")
    doc = await _create_document(db_session)

    response = await client.post(
        f"/api/documents/{doc.id}/tags",
        json={"name": "important", "color": "#00ff00"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "important"


@pytest.mark.asyncio
async def test_remove_tag_from_document(client: AsyncClient, db_session: AsyncSession):
    """Test removing a tag from a document."""
    _, token = await _create_user_and_token(db_session, username="tagrem")
    doc = await _create_document(db_session)

    # Add tag first
    add_resp = await client.post(
        f"/api/documents/{doc.id}/tags",
        json={"name": "removeme"},
        headers={"Authorization": f"Bearer {token}"},
    )
    tag_id = add_resp.json()["id"]

    # Remove it
    response = await client.delete(
        f"/api/documents/{doc.id}/tags/{tag_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 204


@pytest.mark.asyncio
async def test_list_document_tags(client: AsyncClient, db_session: AsyncSession):
    """Test listing tags for a document."""
    _, token = await _create_user_and_token(db_session, username="taglistdoc")
    doc = await _create_document(db_session)

    # Add two tags
    await client.post(
        f"/api/documents/{doc.id}/tags",
        json={"name": "tag_a"},
        headers={"Authorization": f"Bearer {token}"},
    )
    await client.post(
        f"/api/documents/{doc.id}/tags",
        json={"name": "tag_b"},
        headers={"Authorization": f"Bearer {token}"},
    )

    response = await client.get(
        f"/api/documents/{doc.id}/tags",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    names = [t["name"] for t in data]
    assert "tag_a" in names
    assert "tag_b" in names


@pytest.mark.asyncio
async def test_tags_require_auth(client: AsyncClient, db_session: AsyncSession):
    """Test that tag endpoints require authentication."""
    response = await client.get("/api/tags")
    assert response.status_code == 401
