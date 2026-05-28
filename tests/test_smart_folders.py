import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password
from app.models.document import Document, DocumentStatus
from app.models.group import Group
from app.models.user import User


async def _create_user_and_token(
    db: AsyncSession, username: str = "sfuser"
) -> tuple[User, str]:
    user = User(
        username=username,
        email=f"{username}@example.com",
        display_name="Smart Folder User",
        hashed_password=hash_password("password123"),
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    token = create_access_token(data={"sub": user.username})
    return user, token


async def _create_group_and_document(
    db: AsyncSession, filename: str = "test.pdf"
) -> tuple[Group, Document]:
    group = Group(name="SF Test Group")
    db.add(group)
    await db.flush()
    await db.refresh(group)
    doc = Document(
        group_id=group.id,
        original_filename=filename,
        storage_path="/tmp/sf_test.pdf",
        file_type="application/pdf",
        file_size=1024,
        status=DocumentStatus.uploaded,
    )
    db.add(doc)
    await db.flush()
    await db.refresh(doc)
    return group, doc


@pytest.mark.asyncio
async def test_create_smart_folder(client: AsyncClient, db_session: AsyncSession):
    """Test creating a smart folder."""
    _, token = await _create_user_and_token(db_session)

    response = await client.post(
        "/api/smart-folders",
        json={
            "name": "My Smart Folder",
            "description": "Finds PDFs",
            "query_json": {"filename_contains": "report"},
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "My Smart Folder"
    assert data["description"] == "Finds PDFs"
    assert data["query_json"] == {"filename_contains": "report"}
    assert "id" in data


@pytest.mark.asyncio
async def test_list_smart_folders(client: AsyncClient, db_session: AsyncSession):
    """Test listing smart folders for current user."""
    _, token = await _create_user_and_token(db_session, username="sflist")

    await client.post(
        "/api/smart-folders",
        json={"name": "Folder A", "query_json": {"status": "uploaded"}},
        headers={"Authorization": f"Bearer {token}"},
    )
    await client.post(
        "/api/smart-folders",
        json={"name": "Folder B", "query_json": {"status": "uploaded"}},
        headers={"Authorization": f"Bearer {token}"},
    )

    response = await client.get(
        "/api/smart-folders",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 2
    names = [f["name"] for f in data]
    assert "Folder A" in names
    assert "Folder B" in names


@pytest.mark.asyncio
async def test_get_smart_folder_by_id(client: AsyncClient, db_session: AsyncSession):
    """Test getting a smart folder by ID."""
    _, token = await _create_user_and_token(db_session, username="sfget")

    create_resp = await client.post(
        "/api/smart-folders",
        json={"name": "Get Me", "query_json": {"status": "uploaded"}},
        headers={"Authorization": f"Bearer {token}"},
    )
    folder_id = create_resp.json()["id"]

    response = await client.get(
        f"/api/smart-folders/{folder_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Get Me"


@pytest.mark.asyncio
async def test_update_smart_folder(client: AsyncClient, db_session: AsyncSession):
    """Test updating a smart folder."""
    _, token = await _create_user_and_token(db_session, username="sfupdate")

    create_resp = await client.post(
        "/api/smart-folders",
        json={"name": "Original", "query_json": {"status": "uploaded"}},
        headers={"Authorization": f"Bearer {token}"},
    )
    folder_id = create_resp.json()["id"]

    response = await client.put(
        f"/api/smart-folders/{folder_id}",
        json={"name": "Updated Name", "query_json": {"filename_contains": "new"}},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Updated Name"
    assert data["query_json"] == {"filename_contains": "new"}


@pytest.mark.asyncio
async def test_delete_smart_folder(client: AsyncClient, db_session: AsyncSession):
    """Test deleting a smart folder."""
    _, token = await _create_user_and_token(db_session, username="sfdel")

    create_resp = await client.post(
        "/api/smart-folders",
        json={"name": "Delete Me", "query_json": {}},
        headers={"Authorization": f"Bearer {token}"},
    )
    folder_id = create_resp.json()["id"]

    response = await client.delete(
        f"/api/smart-folders/{folder_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 204

    # Verify it's gone
    get_resp = await client.get(
        f"/api/smart-folders/{folder_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_smart_folder_execute_query(
    client: AsyncClient, db_session: AsyncSession
):
    """Test executing a smart folder query returns matching documents."""
    _, token = await _create_user_and_token(db_session, username="sfexec")
    group, doc = await _create_group_and_document(db_session, filename="report_2024.pdf")

    # Create smart folder that matches by filename
    create_resp = await client.post(
        "/api/smart-folders",
        json={
            "name": "Reports",
            "query_json": {"filename_contains": "report"},
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    folder_id = create_resp.json()["id"]

    response = await client.get(
        f"/api/smart-folders/{folder_id}/documents",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    assert doc.id in data["document_ids"]


@pytest.mark.asyncio
async def test_smart_folder_not_found(client: AsyncClient, db_session: AsyncSession):
    """Test getting a non-existent smart folder returns 404."""
    _, token = await _create_user_and_token(db_session, username="sfnf")

    response = await client.get(
        "/api/smart-folders/99999",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404
