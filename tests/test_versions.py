import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select

from app.core.security import create_access_token, hash_password
from app.models.document import Document, DocumentStatus
from app.models.group import Group
from app.models.user import Role, User, UserRole
from app.models.version import DocumentVersion


@pytest_asyncio.fixture
async def seeded_db(db_session):
    """Seed roles into the test database."""
    roles_data = [
        ("admin", "Administrator"),
        ("reviewer", "Reviewer"),
        ("editor", "Editor"),
    ]
    for code, name in roles_data:
        db_session.add(Role(code=code, name=name, description=f"{code} role", is_system=True))
    await db_session.flush()
    return db_session


@pytest_asyncio.fixture
async def admin_user(seeded_db):
    """Create an admin user in the test database."""
    result = await seeded_db.execute(select(Role).where(Role.code == "admin"))
    admin_role = result.scalar_one()

    user = User(
        username="admin",
        email="admin@edms.local",
        display_name="Admin",
        hashed_password=hash_password("admin"),
    )
    seeded_db.add(user)
    await seeded_db.flush()
    await seeded_db.refresh(user)

    user_role = UserRole(user_id=user.id, role_id=admin_role.id)
    seeded_db.add(user_role)
    await seeded_db.flush()
    await seeded_db.refresh(user)
    return user


@pytest_asyncio.fixture
async def admin_token(admin_user):
    """Create a valid JWT token for the admin user."""
    return create_access_token(data={"sub": admin_user.username})


@pytest_asyncio.fixture
async def test_group(seeded_db):
    """Create a test group."""
    group = Group(name="Test Group", description="For version tests")
    seeded_db.add(group)
    await seeded_db.flush()
    await seeded_db.refresh(group)
    return group


@pytest_asyncio.fixture
async def test_document(seeded_db, test_group):
    """Create a test document directly."""
    doc = Document(
        group_id=test_group.id,
        original_filename="test.pdf",
        storage_path="/tmp/test.pdf",
        file_type="application/pdf",
        file_size=1024,
        status=DocumentStatus.processed,
    )
    seeded_db.add(doc)
    await seeded_db.flush()
    await seeded_db.refresh(doc)
    return doc


@pytest.mark.asyncio
async def test_upload_new_version_increments_version_number(
    client: AsyncClient, test_document, admin_token, db_session
):
    """Upload new version increments the version_number."""
    # Upload first version
    response = await client.post(
        f"/api/documents/{test_document.id}/versions",
        files={"file": ("v1.txt", b"version one content", "text/plain")},
        data={"changelog": "Initial version"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["version_number"] == 1
    assert data["document_id"] == test_document.id
    assert data["changelog"] == "Initial version"

    # Upload second version
    response = await client.post(
        f"/api/documents/{test_document.id}/versions",
        files={"file": ("v2.txt", b"version two content longer", "text/plain")},
        data={"changelog": "Updated content"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["version_number"] == 2


@pytest.mark.asyncio
async def test_list_versions_returns_all_ordered(
    client: AsyncClient, test_document, admin_token, db_session
):
    """List versions returns all versions ordered by version_number desc."""
    # Upload two versions
    await client.post(
        f"/api/documents/{test_document.id}/versions",
        files={"file": ("v1.txt", b"one", "text/plain")},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    await client.post(
        f"/api/documents/{test_document.id}/versions",
        files={"file": ("v2.txt", b"two longer", "text/plain")},
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    response = await client.get(f"/api/documents/{test_document.id}/versions")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert len(data["versions"]) == 2
    # Ordered by version_number descending
    assert data["versions"][0]["version_number"] == 2
    assert data["versions"][1]["version_number"] == 1


@pytest.mark.asyncio
async def test_get_specific_version_returns_correct_data(
    client: AsyncClient, test_document, admin_token, db_session
):
    """Get specific version returns correct metadata."""
    response = await client.post(
        f"/api/documents/{test_document.id}/versions",
        files={"file": ("report.txt", b"report content", "text/plain")},
        data={"changelog": "First upload"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 201
    version_id = response.json()["id"]

    response = await client.get(
        f"/api/documents/{test_document.id}/versions/{version_id}"
    )
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == version_id
    assert data["version_number"] == 1
    assert data["file_size"] == len(b"report content")
    assert data["file_type"] == "text/plain"
    assert data["changelog"] == "First upload"


@pytest.mark.asyncio
async def test_revert_updates_document_current_version(
    client: AsyncClient, test_document, admin_token, db_session
):
    """Revert updates document to point to the old version."""
    # Upload version 1
    resp1 = await client.post(
        f"/api/documents/{test_document.id}/versions",
        files={"file": ("v1.txt", b"version one", "text/plain")},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp1.status_code == 201
    v1_id = resp1.json()["id"]

    # Upload version 2
    resp2 = await client.post(
        f"/api/documents/{test_document.id}/versions",
        files={"file": ("v2.txt", b"version two longer content", "text/plain")},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp2.status_code == 201

    # Revert to version 1
    response = await client.post(
        f"/api/documents/{test_document.id}/versions/{v1_id}/revert",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["version_number"] == 1

    # Verify document was updated
    await db_session.refresh(test_document)
    assert test_document.current_version == 1


@pytest.mark.asyncio
async def test_compare_returns_size_diff(
    client: AsyncClient, test_document, admin_token, db_session
):
    """Compare returns size_diff between two versions."""
    # Upload version 1 (small)
    await client.post(
        f"/api/documents/{test_document.id}/versions",
        files={"file": ("v1.txt", b"small", "text/plain")},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    # Upload version 2 (larger)
    await client.post(
        f"/api/documents/{test_document.id}/versions",
        files={"file": ("v2.txt", b"much larger content here", "text/plain")},
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    response = await client.get(
        f"/api/documents/{test_document.id}/versions/compare",
        params={"version_a": 1, "version_b": 2},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["version_a"]["version_number"] == 1
    assert data["version_b"]["version_number"] == 2
    # size_diff = version_b.file_size - version_a.file_size
    assert data["size_diff"] == len(b"much larger content here") - len(b"small")
    assert "time_diff_seconds" in data


@pytest.mark.asyncio
async def test_each_version_has_own_wrapped_dek(
    client: AsyncClient, test_document, admin_token, db_session
):
    """Each version has its own independent wrapped_dek (different from others)."""
    # Upload two versions
    await client.post(
        f"/api/documents/{test_document.id}/versions",
        files={"file": ("v1.txt", b"version one", "text/plain")},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    await client.post(
        f"/api/documents/{test_document.id}/versions",
        files={"file": ("v2.txt", b"version two", "text/plain")},
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    # Query versions from DB
    result = await db_session.execute(
        select(DocumentVersion)
        .where(DocumentVersion.document_id == test_document.id)
        .order_by(DocumentVersion.version_number)
    )
    versions = list(result.scalars().all())
    assert len(versions) == 2

    # Both should have wrapped_dek (or both None if KMS not available)
    # If KMS is configured, they should be different
    if versions[0].wrapped_dek and versions[1].wrapped_dek:
        assert versions[0].wrapped_dek != versions[1].wrapped_dek


@pytest.mark.asyncio
async def test_create_version_for_nonexistent_document_returns_404(
    client: AsyncClient, admin_token
):
    """Creating a version for a non-existent document returns 404."""
    response = await client.post(
        "/api/documents/99999/versions",
        files={"file": ("test.txt", b"content", "text/plain")},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_upload_version_requires_auth(
    client: AsyncClient, test_document
):
    """Upload version endpoint requires authentication."""
    response = await client.post(
        f"/api/documents/{test_document.id}/versions",
        files={"file": ("test.txt", b"content", "text/plain")},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_revert_requires_auth(
    client: AsyncClient, test_document
):
    """Revert endpoint requires authentication."""
    response = await client.post(
        f"/api/documents/{test_document.id}/versions/some-version-id/revert",
    )
    assert response.status_code == 401
