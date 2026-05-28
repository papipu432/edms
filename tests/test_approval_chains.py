import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password
from app.models.document import Document, DocumentStatus
from app.models.group import Group
from app.models.template import DocumentTemplate
from app.models.user import Role, User, UserRole


async def _create_user_with_roles(
    db: AsyncSession, roles: list[str] | None = None, username: str = "testuser"
) -> tuple[User, str]:
    """Helper to create a user with specified roles and return (user, token)."""
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
            user_role = UserRole(user_id=user.id, role_id=role.id)
            db.add(user_role)
        await db.flush()
        await db.refresh(user)

    token = create_access_token(data={"sub": user.username})
    return user, token


async def _create_document(db: AsyncSession, group: Group | None = None, template_id: int | None = None) -> Document:
    """Helper to create a group and document."""
    if group is None:
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
        template_id=template_id,
    )
    db.add(doc)
    await db.flush()
    await db.refresh(doc)
    return doc


@pytest.mark.asyncio
async def test_create_approval_chain(client: AsyncClient, db_session: AsyncSession):
    user, token = await _create_user_with_roles(db_session, ["admin"])

    response = await client.post(
        "/api/approval-chains",
        json={
            "name": "Test Chain",
            "steps": [
                {"step_order": 1, "approval_type": "sequential", "role_code": "reviewer"},
                {"step_order": 2, "approval_type": "sequential", "role_code": "approver"},
            ],
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Test Chain"
    assert len(data["steps"]) == 2
    assert data["steps"][0]["step_order"] == 1
    assert data["steps"][1]["step_order"] == 2


@pytest.mark.asyncio
async def test_list_approval_chains(client: AsyncClient, db_session: AsyncSession):
    user, token = await _create_user_with_roles(db_session, ["admin"])

    await client.post(
        "/api/approval-chains",
        json={"name": "Chain A", "steps": []},
        headers={"Authorization": f"Bearer {token}"},
    )
    await client.post(
        "/api/approval-chains",
        json={"name": "Chain B", "steps": []},
        headers={"Authorization": f"Bearer {token}"},
    )

    response = await client.get("/api/approval-chains")
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 2


@pytest.mark.asyncio
async def test_get_approval_chain_detail(client: AsyncClient, db_session: AsyncSession):
    user, token = await _create_user_with_roles(db_session, ["admin"])

    create_resp = await client.post(
        "/api/approval-chains",
        json={
            "name": "Detail Chain",
            "steps": [
                {"step_order": 1, "approval_type": "sequential", "role_code": "reviewer"},
            ],
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    chain_id = create_resp.json()["id"]

    response = await client.get(f"/api/approval-chains/{chain_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Detail Chain"
    assert len(data["steps"]) == 1


@pytest.mark.asyncio
async def test_delete_approval_chain(client: AsyncClient, db_session: AsyncSession):
    user, token = await _create_user_with_roles(db_session, ["admin"])

    create_resp = await client.post(
        "/api/approval-chains",
        json={"name": "To Delete", "steps": []},
        headers={"Authorization": f"Bearer {token}"},
    )
    chain_id = create_resp.json()["id"]

    response = await client.delete(
        f"/api/approval-chains/{chain_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 204

    # Verify deleted
    response = await client.get(f"/api/approval-chains/{chain_id}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_submit_document_for_approval(client: AsyncClient, db_session: AsyncSession):
    user, token = await _create_user_with_roles(db_session, ["admin"])

    # Create a group and chain matching it
    group = Group(name="Approval Group")
    db_session.add(group)
    await db_session.flush()
    await db_session.refresh(group)

    await client.post(
        "/api/approval-chains",
        json={
            "name": "Folder Chain",
            "folder_id": group.id,
            "steps": [
                {"step_order": 1, "approval_type": "sequential", "role_code": "reviewer"},
                {"step_order": 2, "approval_type": "sequential", "role_code": "approver"},
            ],
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    doc = await _create_document(db_session, group=group)

    response = await client.post(
        f"/api/documents/{doc.id}/approval-requests",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["document_id"] == doc.id
    assert data["status"] == "pending"
    assert data["current_step_order"] == 1


@pytest.mark.asyncio
async def test_approve_steps_sequentially(client: AsyncClient, db_session: AsyncSession):
    user, token = await _create_user_with_roles(db_session, ["admin"])

    group = Group(name="Sequential Group")
    db_session.add(group)
    await db_session.flush()
    await db_session.refresh(group)

    await client.post(
        "/api/approval-chains",
        json={
            "name": "Sequential Chain",
            "folder_id": group.id,
            "steps": [
                {"step_order": 1, "approval_type": "sequential", "role_code": "reviewer"},
                {"step_order": 2, "approval_type": "sequential", "role_code": "approver"},
            ],
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    doc = await _create_document(db_session, group=group)

    # Submit for approval
    submit_resp = await client.post(
        f"/api/documents/{doc.id}/approval-requests",
        headers={"Authorization": f"Bearer {token}"},
    )
    request_id = submit_resp.json()["id"]

    # Approve step 1
    resp1 = await client.post(
        f"/api/approval-requests/{request_id}/decide",
        json={"decision": "approved", "comment": "Step 1 OK"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp1.status_code == 201

    # Check status - should be on step 2
    status_resp = await client.get(
        f"/api/documents/{doc.id}/approval-status",
    )
    assert status_resp.json()["current_step_order"] == 2
    assert status_resp.json()["status"] == "pending"

    # Approve step 2
    resp2 = await client.post(
        f"/api/approval-requests/{request_id}/decide",
        json={"decision": "approved"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp2.status_code == 201

    # Check status - should be approved
    status_resp = await client.get(
        f"/api/documents/{doc.id}/approval-status",
    )
    assert status_resp.json()["status"] == "approved"


@pytest.mark.asyncio
async def test_reject_step(client: AsyncClient, db_session: AsyncSession):
    user, token = await _create_user_with_roles(db_session, ["admin"])

    group = Group(name="Reject Group")
    db_session.add(group)
    await db_session.flush()
    await db_session.refresh(group)

    await client.post(
        "/api/approval-chains",
        json={
            "name": "Reject Chain",
            "folder_id": group.id,
            "steps": [
                {"step_order": 1, "approval_type": "sequential", "role_code": "reviewer"},
                {"step_order": 2, "approval_type": "sequential", "role_code": "approver"},
            ],
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    doc = await _create_document(db_session, group=group)

    submit_resp = await client.post(
        f"/api/documents/{doc.id}/approval-requests",
        headers={"Authorization": f"Bearer {token}"},
    )
    request_id = submit_resp.json()["id"]

    # Reject at step 1
    resp = await client.post(
        f"/api/approval-requests/{request_id}/decide",
        json={"decision": "rejected", "comment": "Not good enough"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201

    # Status should be rejected
    status_resp = await client.get(f"/api/documents/{doc.id}/approval-status")
    assert status_resp.json()["status"] == "rejected"


@pytest.mark.asyncio
async def test_chain_not_found_for_unmatched_document(client: AsyncClient, db_session: AsyncSession):
    user, token = await _create_user_with_roles(db_session, ["admin"])

    # Create a document with no matching chain
    group = Group(name="No Chain Group")
    db_session.add(group)
    await db_session.flush()
    await db_session.refresh(group)

    doc = await _create_document(db_session, group=group)

    response = await client.post(
        f"/api/documents/{doc.id}/approval-requests",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404
    assert "No approval chain found" in response.json()["detail"]


@pytest.mark.asyncio
async def test_approval_chain_matched_by_template(client: AsyncClient, db_session: AsyncSession):
    user, token = await _create_user_with_roles(db_session, ["admin"])

    # Create a template
    template = DocumentTemplate(name="Invoice Template")
    db_session.add(template)
    await db_session.flush()
    await db_session.refresh(template)

    # Create chain matching template
    await client.post(
        "/api/approval-chains",
        json={
            "name": "Template Chain",
            "template_id": template.id,
            "steps": [
                {"step_order": 1, "approval_type": "sequential", "role_code": "approver"},
            ],
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    # Create document with that template
    doc = await _create_document(db_session, template_id=template.id)

    response = await client.post(
        f"/api/documents/{doc.id}/approval-requests",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    assert response.json()["status"] == "pending"


@pytest.mark.asyncio
async def test_create_chain_requires_admin(client: AsyncClient, db_session: AsyncSession):
    user, token = await _create_user_with_roles(db_session, ["editor"], username="editor_user")

    response = await client.post(
        "/api/approval-chains",
        json={"name": "Should Fail", "steps": []},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403
