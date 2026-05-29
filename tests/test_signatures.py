import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password
from app.models.document import Document, DocumentStatus
from app.models.group import Group
from app.models.user import Role, User, UserRole


async def _create_user(
    db: AsyncSession, username: str = "signeruser", roles: list[str] | None = None
) -> tuple[User, str]:
    """Helper to create a user and return (user, token)."""
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
            db.add(UserRole(user_id=user.id, role_id=role.id))
        await db.flush()
        await db.refresh(user)

    token = create_access_token(data={"sub": user.username})
    return user, token


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
async def test_sign_document(client: AsyncClient, db_session: AsyncSession):
    user, token = await _create_user(db_session)
    doc = await _create_document(db_session)

    response = await client.post(
        f"/api/documents/{doc.id}/sign",
        json={},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["document_id"] == doc.id
    assert data["signer_id"] == user.id
    assert data["signature_hash"] is not None
    assert len(data["signature_hash"]) == 64  # SHA-256 hex
    assert data["is_valid"] is True
    assert data["verification_url"] is not None
    assert "/api/signatures/verify/" in data["verification_url"]


@pytest.mark.asyncio
async def test_sign_document_with_qr_code(client: AsyncClient, db_session: AsyncSession):
    user, token = await _create_user(db_session)
    doc = await _create_document(db_session)

    response = await client.post(
        f"/api/documents/{doc.id}/sign",
        json={},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["qr_code_path"] is not None
    assert data["qr_code_path"].endswith(".png")


@pytest.mark.asyncio
async def test_verify_signature_public(client: AsyncClient, db_session: AsyncSession):
    user, token = await _create_user(db_session)
    doc = await _create_document(db_session)

    # Sign the document
    sign_resp = await client.post(
        f"/api/documents/{doc.id}/sign",
        json={},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert sign_resp.status_code == 201
    sig_hash = sign_resp.json()["signature_hash"]

    # Verify without authentication
    verify_resp = await client.get(f"/api/signatures/verify/{sig_hash}")
    assert verify_resp.status_code == 200
    data = verify_resp.json()
    assert data["valid"] is True
    assert data["document_id"] == doc.id
    assert data["signer_username"] == user.username
    assert data["signed_at"] is not None


@pytest.mark.asyncio
async def test_verify_invalid_hash(client: AsyncClient, db_session: AsyncSession):
    # Verify with a non-existent hash - no auth needed
    verify_resp = await client.get("/api/signatures/verify/invalidhash123")
    assert verify_resp.status_code == 200
    data = verify_resp.json()
    assert data["valid"] is False


@pytest.mark.asyncio
async def test_list_signatures_for_document(client: AsyncClient, db_session: AsyncSession):
    user, token = await _create_user(db_session)
    doc = await _create_document(db_session)

    # Sign the document
    await client.post(
        f"/api/documents/{doc.id}/sign",
        json={},
        headers={"Authorization": f"Bearer {token}"},
    )

    # List signatures
    response = await client.get(
        f"/api/documents/{doc.id}/signatures",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["document_id"] == doc.id


@pytest.mark.asyncio
async def test_sign_nonexistent_document(client: AsyncClient, db_session: AsyncSession):
    user, token = await _create_user(db_session)

    response = await client.post(
        "/api/documents/9999/sign",
        json={},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404
