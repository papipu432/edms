"""Tests for offline package generation."""

import json
import zipfile
from io import BytesIO

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password
from app.models.document import Document, DocumentStatus
from app.models.group import Group
from app.models.user import Role, User, UserRole
from app.services.offline_package import OfflinePackageService


async def _create_admin_user(db: AsyncSession, username: str = "admin") -> tuple[User, str]:
    """Create an admin user and return (user, token)."""
    existing = await db.execute(select(Role).where(Role.code == "admin"))
    if existing.scalar_one_or_none() is None:
        db.add(Role(code="admin", name="Admin", description="Admin role", is_system=True))
    await db.flush()

    user = User(
        username=username,
        email=f"{username}@example.com",
        display_name="Admin User",
        hashed_password=hash_password("password123"),
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)

    result = await db.execute(select(Role).where(Role.code == "admin"))
    role = result.scalar_one()
    user_role = UserRole(user_id=user.id, role_id=role.id)
    db.add(user_role)
    await db.flush()
    await db.refresh(user)

    token = create_access_token(data={"sub": user.username})
    return user, token


async def _create_document(db: AsyncSession, group: Group, filename: str) -> Document:
    doc = Document(
        group_id=group.id,
        original_filename=filename,
        storage_path=f"/tmp/{filename}",
        file_type="application/pdf",
        file_size=1024,
        status=DocumentStatus.uploaded,
    )
    db.add(doc)
    await db.flush()
    await db.refresh(doc)
    return doc


@pytest.mark.asyncio
async def test_generate_offline_package_with_document_ids(client: AsyncClient, db_session: AsyncSession):
    """Test generating an offline package with specific document IDs."""
    _, token = await _create_admin_user(db_session)

    group = Group(name="Offline Group")
    db_session.add(group)
    await db_session.flush()
    await db_session.refresh(group)

    doc1 = await _create_document(db_session, group, "doc1.pdf")
    doc2 = await _create_document(db_session, group, "doc2.pdf")

    response = await client.post(
        "/api/offline/generate",
        json={"document_ids": [doc1.id, doc2.id]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"

    # Verify ZIP contents
    zip_buffer = BytesIO(response.content)
    with zipfile.ZipFile(zip_buffer, "r") as zf:
        names = zf.namelist()
        assert "metadata.json" in names
        assert "index.html" in names
        assert "search_index.json" in names

        # Verify metadata
        metadata = json.loads(zf.read("metadata.json"))
        assert len(metadata) == 2

        # Verify index.html contains viewer
        html = zf.read("index.html").decode("utf-8")
        assert "EDMS Offline Viewer" in html


@pytest.mark.asyncio
async def test_generate_offline_package_with_group_id(client: AsyncClient, db_session: AsyncSession):
    """Test generating an offline package for a group."""
    _, token = await _create_admin_user(db_session)

    group = Group(name="Group Offline")
    db_session.add(group)
    await db_session.flush()
    await db_session.refresh(group)

    await _create_document(db_session, group, "grp_doc1.pdf")
    await _create_document(db_session, group, "grp_doc2.pdf")

    response = await client.post(
        "/api/offline/generate",
        json={"group_id": group.id},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200

    zip_buffer = BytesIO(response.content)
    with zipfile.ZipFile(zip_buffer, "r") as zf:
        metadata = json.loads(zf.read("metadata.json"))
        assert len(metadata) == 2


@pytest.mark.asyncio
async def test_offline_package_service_directly(db_session: AsyncSession):
    """Test the offline package service directly."""
    service = OfflinePackageService()

    group = Group(name="Direct Test")
    db_session.add(group)
    await db_session.flush()
    await db_session.refresh(group)

    doc = Document(
        group_id=group.id,
        original_filename="direct.pdf",
        storage_path="/tmp/direct.pdf",
        file_type="application/pdf",
        file_size=512,
        status=DocumentStatus.uploaded,
    )
    db_session.add(doc)
    await db_session.flush()
    await db_session.refresh(doc)

    buffer = await service.generate_package(db_session, document_ids=[doc.id])
    assert buffer is not None

    with zipfile.ZipFile(buffer, "r") as zf:
        assert "index.html" in zf.namelist()
        assert "metadata.json" in zf.namelist()


@pytest.mark.asyncio
async def test_offline_package_empty(client: AsyncClient, db_session: AsyncSession):
    """Test generating an offline package with no matching documents."""
    _, token = await _create_admin_user(db_session)

    response = await client.post(
        "/api/offline/generate",
        json={"document_ids": [99999]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200

    zip_buffer = BytesIO(response.content)
    with zipfile.ZipFile(zip_buffer, "r") as zf:
        metadata = json.loads(zf.read("metadata.json"))
        assert metadata == []
