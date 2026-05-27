import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password
from app.models.document import Document, DocumentStatus
from app.models.group import Group
from app.models.user import Role, RoleName, User


async def _create_user_with_roles(
    db: AsyncSession, roles: list[RoleName] | None = None
) -> tuple[User, str]:
    """Helper to create a user with specified roles and return (user, token)."""
    # Ensure role records exist
    if roles:
        for role_name in roles:
            existing = await db.execute(select(Role).where(Role.name == role_name))
            if existing.scalar_one_or_none() is None:
                db.add(Role(name=role_name, description=f"{role_name.value} role"))
        await db.flush()

    user = User(
        username="testuser",
        email="test@example.com",
        hashed_password=hash_password("password123"),
    )

    if roles:
        for role_name in roles:
            result = await db.execute(select(Role).where(Role.name == role_name))
            role = result.scalar_one()
            user.roles.append(role)

    db.add(user)
    await db.flush()
    await db.refresh(user)
    token = create_access_token(data={"sub": user.username})
    return user, token


async def _create_user_and_token(db: AsyncSession) -> tuple[User, str]:
    """Helper to create a user with admin role and return (user, token)."""
    return await _create_user_with_roles(db, [RoleName.admin])


async def _create_document(db: AsyncSession) -> Document:
    """Helper to create a group and document."""
    group = Group(name="Test Group")
    db.add(group)
    await db.flush()
    await db.refresh(group)
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
async def test_create_annotation(client: AsyncClient, db_session: AsyncSession):
    user, token = await _create_user_and_token(db_session)
    doc = await _create_document(db_session)

    response = await client.post(
        f"/api/documents/{doc.id}/annotations",
        json={"text": "This is a test annotation", "start_offset": 0, "end_offset": 10},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["text"] == "This is a test annotation"
    assert data["document_id"] == doc.id
    assert data["user_id"] == user.id
    assert data["start_offset"] == 0
    assert data["end_offset"] == 10


@pytest.mark.asyncio
async def test_list_annotations(client: AsyncClient, db_session: AsyncSession):
    user, token = await _create_user_and_token(db_session)
    doc = await _create_document(db_session)

    # Create two annotations
    await client.post(
        f"/api/documents/{doc.id}/annotations",
        json={"text": "First annotation"},
        headers={"Authorization": f"Bearer {token}"},
    )
    await client.post(
        f"/api/documents/{doc.id}/annotations",
        json={"text": "Second annotation"},
        headers={"Authorization": f"Bearer {token}"},
    )

    # List annotations (public - no auth required)
    response = await client.get(f"/api/documents/{doc.id}/annotations")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["text"] == "First annotation"
    assert data[1]["text"] == "Second annotation"


@pytest.mark.asyncio
async def test_annotation_requires_auth(client: AsyncClient, db_session: AsyncSession):
    doc = await _create_document(db_session)

    response = await client.post(
        f"/api/documents/{doc.id}/annotations",
        json={"text": "Should fail"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_annotation_document_not_found(client: AsyncClient, db_session: AsyncSession):
    user, token = await _create_user_and_token(db_session)

    response = await client.post(
        "/api/documents/9999/annotations",
        json={"text": "Should fail"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_list_annotations_document_not_found(client: AsyncClient, db_session: AsyncSession):
    response = await client.get("/api/documents/9999/annotations")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_workflow_submit_review(client: AsyncClient, db_session: AsyncSession):
    user, token = await _create_user_with_roles(db_session, [RoleName.editor])
    doc = await _create_document(db_session)

    response = await client.post(
        f"/api/documents/{doc.id}/workflow/submit_review",
        json={"comment": "Ready for review"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["action"] == "submit_review"
    assert data["comment"] == "Ready for review"
    assert data["document_id"] == doc.id


@pytest.mark.asyncio
async def test_workflow_approve(client: AsyncClient, db_session: AsyncSession):
    user, token = await _create_user_with_roles(db_session, [RoleName.approver])
    doc = await _create_document(db_session)

    response = await client.post(
        f"/api/documents/{doc.id}/workflow/approve",
        json={"comment": "Looks good"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["action"] == "approve"


@pytest.mark.asyncio
async def test_workflow_reject(client: AsyncClient, db_session: AsyncSession):
    user, token = await _create_user_with_roles(db_session, [RoleName.reviewer])
    doc = await _create_document(db_session)

    response = await client.post(
        f"/api/documents/{doc.id}/workflow/reject",
        json={"comment": "Needs corrections"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["action"] == "reject"
    assert data["comment"] == "Needs corrections"


@pytest.mark.asyncio
async def test_workflow_request_changes(client: AsyncClient, db_session: AsyncSession):
    user, token = await _create_user_with_roles(db_session, [RoleName.reviewer])
    doc = await _create_document(db_session)

    response = await client.post(
        f"/api/documents/{doc.id}/workflow/request_changes",
        json={"comment": "Please update section 2"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["action"] == "request_changes"


@pytest.mark.asyncio
async def test_workflow_history(client: AsyncClient, db_session: AsyncSession):
    user, token = await _create_user_with_roles(db_session, [RoleName.admin])
    doc = await _create_document(db_session)

    # Perform multiple actions
    await client.post(
        f"/api/documents/{doc.id}/workflow/submit_review",
        json={"comment": "Submitted"},
        headers={"Authorization": f"Bearer {token}"},
    )
    await client.post(
        f"/api/documents/{doc.id}/workflow/approve",
        json={},
        headers={"Authorization": f"Bearer {token}"},
    )

    # Get history (public)
    response = await client.get(f"/api/documents/{doc.id}/workflow")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["action"] == "submit_review"
    assert data[1]["action"] == "approve"


@pytest.mark.asyncio
async def test_workflow_requires_auth(client: AsyncClient, db_session: AsyncSession):
    doc = await _create_document(db_session)

    response = await client.post(
        f"/api/documents/{doc.id}/workflow/approve",
        json={},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_workflow_document_not_found(client: AsyncClient, db_session: AsyncSession):
    user, token = await _create_user_with_roles(db_session, [RoleName.admin])

    response = await client.post(
        "/api/documents/9999/workflow/approve",
        json={},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_workflow_history_document_not_found(client: AsyncClient, db_session: AsyncSession):
    response = await client.get("/api/documents/9999/workflow")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_workflow_role_enforcement_approve(client: AsyncClient, db_session: AsyncSession):
    """Test that users without the approver role cannot approve."""
    user, token = await _create_user_with_roles(db_session, [RoleName.annotator])
    doc = await _create_document(db_session)

    response = await client.post(
        f"/api/documents/{doc.id}/workflow/approve",
        json={"comment": "Trying to approve"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_workflow_role_enforcement_reject(client: AsyncClient, db_session: AsyncSession):
    """Test that users without the reviewer role cannot reject."""
    user, token = await _create_user_with_roles(db_session, [RoleName.annotator])
    doc = await _create_document(db_session)

    response = await client.post(
        f"/api/documents/{doc.id}/workflow/reject",
        json={"comment": "Trying to reject"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_workflow_role_enforcement_allowed(client: AsyncClient, db_session: AsyncSession):
    """Test that annotator can submit_review."""
    user, token = await _create_user_with_roles(db_session, [RoleName.annotator])
    doc = await _create_document(db_session)

    response = await client.post(
        f"/api/documents/{doc.id}/workflow/submit_review",
        json={"comment": "Submitting"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
