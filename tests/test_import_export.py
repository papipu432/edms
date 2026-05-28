"""Tests for import/export ecosystem."""

import csv
import io
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
from app.services.import_export import ImportExportService


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


def _create_zip_with_manifest() -> BytesIO:
    """Create a ZIP file with a manifest.json for testing."""
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        manifest = {
            "files": [
                {
                    "filename": "report.pdf",
                    "folder_path": "Reports",
                    "file_type": "application/pdf",
                    "file_size": 1024,
                    "tags": ["financial", "q1"],
                },
                {
                    "filename": "memo.docx",
                    "folder_path": "Memos",
                    "file_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    "file_size": 512,
                    "tags": [],
                },
            ]
        }
        zf.writestr("manifest.json", json.dumps(manifest))
        zf.writestr("report.pdf", b"fake pdf content")
        zf.writestr("memo.docx", b"fake docx content")
    buffer.seek(0)
    return buffer


def _create_csv_file() -> BytesIO:
    """Create a CSV file for testing."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["filename", "folder_path", "tags", "lifecycle_type"])
    writer.writerow(["test1.pdf", "Folder A", "tag1,tag2", "permanent"])
    writer.writerow(["test2.pdf", "Folder B", "tag3", "expiring"])
    csv_bytes = output.getvalue().encode("utf-8")
    return BytesIO(csv_bytes)


@pytest.mark.asyncio
async def test_import_zip_with_manifest(client: AsyncClient, db_session: AsyncSession):
    """Test importing a ZIP file with manifest.json."""
    _, token = await _create_admin_user(db_session)

    zip_buffer = _create_zip_with_manifest()
    response = await client.post(
        "/api/import",
        files={"file": ("import.zip", zip_buffer, "application/zip")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["documents_created"] == 2
    assert data["groups_created"] >= 1
    assert data["errors"] == []


@pytest.mark.asyncio
async def test_import_csv(client: AsyncClient, db_session: AsyncSession):
    """Test importing documents via CSV."""
    _, token = await _create_admin_user(db_session)

    csv_buffer = _create_csv_file()
    response = await client.post(
        "/api/import",
        files={"file": ("import.csv", csv_buffer, "text/csv")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["documents_created"] == 2
    assert data["errors"] == []


@pytest.mark.asyncio
async def test_export_documents(client: AsyncClient, db_session: AsyncSession):
    """Test exporting all documents as ZIP."""
    _, token = await _create_admin_user(db_session)

    # Create some documents first
    group = Group(name="Export Group")
    db_session.add(group)
    await db_session.flush()
    await db_session.refresh(group)

    doc = Document(
        group_id=group.id,
        original_filename="export_test.pdf",
        storage_path="/tmp/export_test.pdf",
        file_type="application/pdf",
        file_size=1024,
        status=DocumentStatus.uploaded,
    )
    db_session.add(doc)
    await db_session.flush()

    response = await client.post(
        "/api/export",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"

    zip_buffer = BytesIO(response.content)
    with zipfile.ZipFile(zip_buffer, "r") as zf:
        assert "metadata.json" in zf.namelist()
        metadata = json.loads(zf.read("metadata.json"))
        assert len(metadata) >= 1
        assert metadata[0]["filename"] == "export_test.pdf"


@pytest.mark.asyncio
async def test_import_export_service_zip(db_session: AsyncSession):
    """Test ImportExportService.import_zip directly."""
    service = ImportExportService()
    zip_buffer = _create_zip_with_manifest()
    result = await service.import_zip(db_session, zip_buffer)

    assert result["documents_created"] == 2
    assert result["groups_created"] >= 1
    assert result["errors"] == []


@pytest.mark.asyncio
async def test_import_export_service_csv(db_session: AsyncSession):
    """Test ImportExportService.import_csv directly."""
    service = ImportExportService()
    csv_buffer = _create_csv_file()
    result = await service.import_csv(db_session, csv_buffer)

    assert result["documents_created"] == 2
    assert result["errors"] == []


@pytest.mark.asyncio
async def test_export_empty(client: AsyncClient, db_session: AsyncSession):
    """Test exporting when no documents exist."""
    _, token = await _create_admin_user(db_session)

    response = await client.post(
        "/api/export",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200

    zip_buffer = BytesIO(response.content)
    with zipfile.ZipFile(zip_buffer, "r") as zf:
        metadata = json.loads(zf.read("metadata.json"))
        assert metadata == []
