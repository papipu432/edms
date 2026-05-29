import io

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password
from app.models.document import Document, DocumentStatus
from app.models.group import Group
from app.models.user import Role, User, UserRole


async def _create_user_with_roles(
    db: AsyncSession, roles: list[str], username: str = "bulkuser"
) -> tuple[User, str]:
    """Helper to create a user with specified roles and return (user, token)."""
    for role_code in roles:
        existing = await db.execute(select(Role).where(Role.code == role_code))
        if existing.scalar_one_or_none() is None:
            db.add(
                Role(
                    code=role_code,
                    name=role_code.title(),
                    description=f"{role_code} role",
                    is_system=True,
                )
            )
    await db.flush()

    user = User(
        username=username,
        email=f"{username}@example.com",
        display_name="Bulk Test User",
        hashed_password=hash_password("password123"),
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)

    for role_code in roles:
        result = await db.execute(select(Role).where(Role.code == role_code))
        role = result.scalar_one()
        user_role = UserRole(user_id=user.id, role_id=role.id)
        db.add(user_role)
    await db.flush()
    await db.refresh(user)

    token = create_access_token(data={"sub": user.username})
    return user, token


async def _create_group(db: AsyncSession, name: str = "Test Group") -> Group:
    group = Group(name=name)
    db.add(group)
    await db.flush()
    await db.refresh(group)
    return group


async def _create_document(db: AsyncSession, group: Group) -> Document:
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
async def test_bulk_upload_multiple_files(
    client: AsyncClient, db_session: AsyncSession
):
    """Upload 3 files to a group, verify all created."""
    _, token = await _create_user_with_roles(db_session, ["editor", "admin"])
    group = await _create_group(db_session)

    files = [
        ("files", ("file1.txt", io.BytesIO(b"content1"), "text/plain")),
        ("files", ("file2.txt", io.BytesIO(b"content2"), "text/plain")),
        ("files", ("file3.txt", io.BytesIO(b"content3"), "text/plain")),
    ]

    response = await client.post(
        f"/api/bulk/upload?group_id={group.id}",
        files=files,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 3
    assert data["successful"] == 3
    assert data["failed"] == 0
    assert len(data["results"]) == 3
    for result in data["results"]:
        assert result["success"] is True
        assert result["document_id"] is not None


@pytest.mark.asyncio
async def test_bulk_upload_with_folder_path(
    client: AsyncClient, db_session: AsyncSession
):
    """Upload with folder_path='A/B/C', verify groups created with correct hierarchy."""
    _, token = await _create_user_with_roles(db_session, ["editor", "admin"])

    files = [
        ("files", ("doc.txt", io.BytesIO(b"hello"), "text/plain")),
    ]

    response = await client.post(
        "/api/bulk/upload?folder_path=A/B/C",
        files=files,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["successful"] == 1

    # Verify group hierarchy
    result = await db_session.execute(
        select(Group).where(Group.name == "A", Group.parent_id.is_(None))
    )
    group_a = result.scalar_one_or_none()
    assert group_a is not None

    result = await db_session.execute(
        select(Group).where(Group.name == "B", Group.parent_id == group_a.id)
    )
    group_b = result.scalar_one_or_none()
    assert group_b is not None

    result = await db_session.execute(
        select(Group).where(Group.name == "C", Group.parent_id == group_b.id)
    )
    group_c = result.scalar_one_or_none()
    assert group_c is not None


@pytest.mark.asyncio
async def test_bulk_upload_folder_path_idempotent(
    client: AsyncClient, db_session: AsyncSession
):
    """Upload to same folder_path twice, verify no duplicate groups."""
    _, token = await _create_user_with_roles(db_session, ["editor", "admin"])

    files1 = [("files", ("f1.txt", io.BytesIO(b"a"), "text/plain"))]
    files2 = [("files", ("f2.txt", io.BytesIO(b"b"), "text/plain"))]

    await client.post(
        "/api/bulk/upload?folder_path=X/Y",
        files=files1,
        headers={"Authorization": f"Bearer {token}"},
    )
    await client.post(
        "/api/bulk/upload?folder_path=X/Y",
        files=files2,
        headers={"Authorization": f"Bearer {token}"},
    )

    # Check only one group X and one group Y exist
    result = await db_session.execute(
        select(Group).where(Group.name == "X", Group.parent_id.is_(None))
    )
    groups_x = list(result.scalars().all())
    assert len(groups_x) == 1

    result = await db_session.execute(
        select(Group).where(Group.name == "Y", Group.parent_id == groups_x[0].id)
    )
    groups_y = list(result.scalars().all())
    assert len(groups_y) == 1


@pytest.mark.asyncio
async def test_bulk_approve_multiple_documents(
    client: AsyncClient, db_session: AsyncSession
):
    """Create 3 documents, bulk approve them all."""
    _, token = await _create_user_with_roles(db_session, ["approver", "admin"])
    group = await _create_group(db_session)
    doc1 = await _create_document(db_session, group)
    doc2 = await _create_document(db_session, group)
    doc3 = await _create_document(db_session, group)

    response = await client.post(
        "/api/bulk/approve",
        json={
            "document_ids": [doc1.id, doc2.id, doc3.id],
            "comment": "All approved",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 3
    assert data["successful"] == 3
    assert data["failed"] == 0


@pytest.mark.asyncio
async def test_bulk_signoff_multiple_documents(
    client: AsyncClient, db_session: AsyncSession
):
    """Create 3 documents, bulk signoff them all."""
    _, token = await _create_user_with_roles(db_session, ["approver", "admin"])
    group = await _create_group(db_session)
    doc1 = await _create_document(db_session, group)
    doc2 = await _create_document(db_session, group)
    doc3 = await _create_document(db_session, group)

    response = await client.post(
        "/api/bulk/signoff",
        json={
            "document_ids": [doc1.id, doc2.id, doc3.id],
            "comment": "Signed off",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 3
    assert data["successful"] == 3
    assert data["failed"] == 0


@pytest.mark.asyncio
async def test_bulk_workflow_permission_denied(
    client: AsyncClient, db_session: AsyncSession
):
    """Non-approver user tries bulk approve, gets 403."""
    _, token = await _create_user_with_roles(
        db_session, ["annotator"], username="noapprover"
    )
    group = await _create_group(db_session)
    doc = await _create_document(db_session, group)

    response = await client.post(
        "/api/bulk/approve",
        json={"document_ids": [doc.id], "comment": "Try"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_bulk_workflow_partial_failure(
    client: AsyncClient, db_session: AsyncSession
):
    """Include a non-existent document_id, verify other docs still processed."""
    _, token = await _create_user_with_roles(db_session, ["approver", "admin"])
    group = await _create_group(db_session)
    doc = await _create_document(db_session, group)

    response = await client.post(
        "/api/bulk/workflow",
        json={
            "document_ids": [doc.id, 99999],
            "action": "approve",
            "comment": "Partial",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert data["successful"] == 1
    assert data["failed"] == 1

    # Find the failed result
    failed = [r for r in data["results"] if not r["success"]]
    assert len(failed) == 1
    assert failed[0]["document_id"] == 99999
    assert "not found" in failed[0]["error"].lower()


@pytest.mark.asyncio
async def test_bulk_upload_requires_auth(client: AsyncClient, db_session: AsyncSession):
    """No token returns 401."""
    files = [("files", ("f.txt", io.BytesIO(b"x"), "text/plain"))]
    response = await client.post("/api/bulk/upload?group_id=1", files=files)
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_bulk_workflow_requires_auth(
    client: AsyncClient, db_session: AsyncSession
):
    """No token returns 401."""
    response = await client.post(
        "/api/bulk/workflow",
        json={"document_ids": [1], "action": "approve"},
    )
    assert response.status_code == 401
