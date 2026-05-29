"""Tests for watermarking features."""

import io
import os
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import AsyncClient

from app.core.security import create_access_token, hash_password
from app.models.document import Document
from app.models.group import Group
from app.models.user import Role, User, UserRole
from app.models.watermark import WatermarkConfig
from app.services.watermark import WatermarkService


@pytest_asyncio.fixture
async def seeded_db(db_session):
    """Seed roles into the test database."""
    admin_role = Role(code="admin", name="Administrator", description="Admin role", is_system=True)
    viewer_role = Role(code="viewer", name="Viewer", description="Viewer role", is_system=True)
    db_session.add(admin_role)
    db_session.add(viewer_role)
    await db_session.flush()
    return db_session


@pytest_asyncio.fixture
async def admin_user(seeded_db):
    """Create an admin user."""
    from sqlalchemy import select

    result = await seeded_db.execute(select(Role).where(Role.code == "admin"))
    admin_role = result.scalar_one()

    user = User(
        username="watermark_admin",
        email="watermark_admin@edms.local",
        display_name="Watermark Admin",
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
async def regular_user(seeded_db):
    """Create a non-admin user."""
    from sqlalchemy import select

    result = await seeded_db.execute(select(Role).where(Role.code == "viewer"))
    viewer_role = result.scalar_one()

    user = User(
        username="watermark_viewer",
        email="watermark_viewer@edms.local",
        display_name="Watermark Viewer",
        hashed_password=hash_password("viewer"),
    )
    seeded_db.add(user)
    await seeded_db.flush()
    await seeded_db.refresh(user)

    user_role = UserRole(user_id=user.id, role_id=viewer_role.id)
    seeded_db.add(user_role)
    await seeded_db.flush()
    await seeded_db.refresh(user)
    return user


@pytest_asyncio.fixture
async def admin_token(admin_user):
    return create_access_token(data={"sub": admin_user.username})


@pytest_asyncio.fixture
async def viewer_token(regular_user):
    return create_access_token(data={"sub": regular_user.username})


class TestWatermarkServiceTextRendering:
    """Test watermark text template rendering."""

    def test_render_basic_template(self):
        service = WatermarkService()
        result = service.render_text(
            "{user} - {doc_id} - CONFIDENTIAL",
            user="testuser",
            doc_id="123",
        )
        assert "testuser" in result
        assert "123" in result
        assert "CONFIDENTIAL" in result

    def test_render_with_timestamp(self):
        service = WatermarkService()
        result = service.render_text(
            "{user} - {timestamp}",
            user="admin",
        )
        assert "admin" in result
        # Timestamp should be in the format YYYY-MM-DD HH:MM:SS
        assert "-" in result

    def test_render_with_custom_text(self):
        service = WatermarkService()
        result = service.render_text(
            "{custom_text}",
            custom_text="DRAFT ONLY",
        )
        assert result == "DRAFT ONLY"

    def test_render_empty_variables(self):
        service = WatermarkService()
        result = service.render_text("{user} - {doc_id}", user="", doc_id="")
        assert " - " in result


class TestWatermarkServiceCSS:
    """Test CSS watermark generation."""

    def test_css_diagonal(self):
        service = WatermarkService()
        result = service.generate_css_watermark("CONFIDENTIAL", 0.3, "diagonal")
        assert "CONFIDENTIAL" in result
        assert "rotate" in result
        assert "0.3" in result

    def test_css_center(self):
        service = WatermarkService()
        result = service.generate_css_watermark("DRAFT", 0.5, "center")
        assert "DRAFT" in result
        assert "translate" in result

    def test_css_top(self):
        service = WatermarkService()
        result = service.generate_css_watermark("TOP", 0.4, "top")
        assert "TOP" in result
        assert "top: 20px" in result

    def test_css_bottom(self):
        service = WatermarkService()
        result = service.generate_css_watermark("BOTTOM", 0.2, "bottom")
        assert "BOTTOM" in result
        assert "bottom: 20px" in result


class TestWatermarkServiceImage:
    """Test image watermarking."""

    def test_apply_image_watermark(self):
        """Test that image watermarking produces valid output."""
        from PIL import Image

        service = WatermarkService()

        # Create a simple test image
        img = Image.new("RGB", (200, 200), (255, 255, 255))
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        img_bytes = buffer.getvalue()

        result = service.apply_image_watermark(img_bytes, "TEST", 0.3, "center")
        assert len(result) > 0

        # Verify it's a valid image
        result_img = Image.open(io.BytesIO(result))
        assert result_img.size == (200, 200)

    def test_apply_image_watermark_diagonal(self):
        from PIL import Image

        service = WatermarkService()

        img = Image.new("RGB", (100, 100), (200, 200, 200))
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        img_bytes = buffer.getvalue()

        result = service.apply_image_watermark(img_bytes, "DIAG", 0.5, "diagonal")
        assert len(result) > 0


class TestWatermarkServicePDF:
    """Test PDF watermarking (with mocks where necessary)."""

    def test_apply_pdf_watermark(self, sample_pdf):
        """Test PDF watermarking with a minimal PDF."""
        service = WatermarkService()
        pdf_bytes = sample_pdf.read_bytes()

        result = service.apply_pdf_watermark(pdf_bytes, "WATERMARK", 0.3, "diagonal")
        # Should return bytes (the PDF)
        assert len(result) > 0
        # Should still be a valid PDF
        assert result[:5] == b"%PDF-"


class TestWatermarkConfigAPI:
    """Test watermark config CRUD API."""

    async def test_create_config(self, client: AsyncClient, admin_token, seeded_db):
        resp = await client.post(
            "/api/watermark/configs",
            json={
                "text_template": "{user} - CONFIDENTIAL",
                "opacity": 0.5,
                "position": "diagonal",
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["text_template"] == "{user} - CONFIDENTIAL"
        assert data["opacity"] == 0.5
        assert data["position"] == "diagonal"
        assert data["enabled"] is True

    async def test_create_config_with_group(self, client: AsyncClient, admin_token, seeded_db):
        # Create a group first
        group = Group(name="Test WM Group", description="Test")
        seeded_db.add(group)
        await seeded_db.flush()
        await seeded_db.refresh(group)

        resp = await client.post(
            "/api/watermark/configs",
            json={
                "group_id": group.id,
                "text_template": "{user} - GROUP",
                "opacity": 0.4,
                "position": "center",
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["group_id"] == group.id

    async def test_list_configs(self, client: AsyncClient, admin_token, seeded_db):
        # Create a config
        await client.post(
            "/api/watermark/configs",
            json={"text_template": "TEST", "opacity": 0.3, "position": "top"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        resp = await client.get(
            "/api/watermark/configs",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        assert len(resp.json()) >= 1

    async def test_update_config(self, client: AsyncClient, admin_token, seeded_db):
        # Create a config
        create_resp = await client.post(
            "/api/watermark/configs",
            json={"text_template": "OLD", "opacity": 0.3, "position": "top"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        config_id = create_resp.json()["id"]

        # Update
        resp = await client.put(
            f"/api/watermark/configs/{config_id}",
            json={"text_template": "NEW", "opacity": 0.7, "enabled": False},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["text_template"] == "NEW"
        assert data["opacity"] == 0.7
        assert data["enabled"] is False

    async def test_delete_config(self, client: AsyncClient, admin_token, seeded_db):
        create_resp = await client.post(
            "/api/watermark/configs",
            json={"text_template": "DEL", "opacity": 0.3, "position": "bottom"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        config_id = create_resp.json()["id"]

        resp = await client.delete(
            f"/api/watermark/configs/{config_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200

    async def test_delete_nonexistent_config(self, client: AsyncClient, admin_token, seeded_db):
        resp = await client.delete(
            "/api/watermark/configs/99999",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 404

    async def test_invalid_position(self, client: AsyncClient, admin_token, seeded_db):
        resp = await client.post(
            "/api/watermark/configs",
            json={"text_template": "X", "opacity": 0.3, "position": "invalid"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 400


class TestWatermarkAdminOnly:
    """Test that config endpoints require admin role."""

    async def test_create_config_non_admin(self, client: AsyncClient, viewer_token, seeded_db):
        resp = await client.post(
            "/api/watermark/configs",
            json={"text_template": "X", "opacity": 0.3, "position": "top"},
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert resp.status_code == 403

    async def test_list_configs_non_admin(self, client: AsyncClient, viewer_token, seeded_db):
        resp = await client.get(
            "/api/watermark/configs",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert resp.status_code == 403


class TestWatermarkDocumentEndpoint:
    """Test watermarked document download."""

    async def test_download_watermarked_no_config(self, client: AsyncClient, admin_token, seeded_db):
        """Test 404 when no watermark config exists."""
        # Create group and document
        group = Group(name="WM Doc Group", description="Test")
        seeded_db.add(group)
        await seeded_db.flush()
        await seeded_db.refresh(group)

        doc = Document(
            group_id=group.id,
            original_filename="test.pdf",
            storage_path="/tmp/nonexistent.pdf",
            file_type="application/pdf",
            file_size=100,
        )
        seeded_db.add(doc)
        await seeded_db.flush()
        await seeded_db.refresh(doc)

        resp = await client.post(
            f"/api/documents/{doc.id}/watermarked",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 404

    async def test_download_watermarked_document_not_found(self, client: AsyncClient, admin_token, seeded_db):
        """Test 404 when document doesn't exist."""
        resp = await client.post(
            "/api/documents/99999/watermarked",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 404

    async def test_download_watermarked_image(self, client: AsyncClient, admin_token, seeded_db, tmp_path):
        """Test watermarked image download."""
        from PIL import Image

        # Create group, document, and watermark config
        group = Group(name="WM Image Group", description="Test")
        seeded_db.add(group)
        await seeded_db.flush()
        await seeded_db.refresh(group)

        # Create a test image file
        img_path = tmp_path / "test_image.png"
        img = Image.new("RGB", (100, 100), (255, 0, 0))
        img.save(str(img_path), format="PNG")

        doc = Document(
            group_id=group.id,
            original_filename="test_image.png",
            storage_path=str(img_path),
            file_type="image/png",
            file_size=os.path.getsize(str(img_path)),
        )
        seeded_db.add(doc)
        await seeded_db.flush()
        await seeded_db.refresh(doc)

        # Create a global watermark config
        config = WatermarkConfig(
            group_id=None,
            text_template="{user} - {doc_id}",
            opacity=0.3,
            position="center",
            enabled=True,
        )
        seeded_db.add(config)
        await seeded_db.flush()

        resp = await client.post(
            f"/api/documents/{doc.id}/watermarked",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        assert "image/png" in resp.headers["content-type"]
        assert len(resp.content) > 0

    async def test_download_watermarked_unauthenticated(self, client: AsyncClient, seeded_db):
        """Test that unauthenticated users can't download."""
        resp = await client.post("/api/documents/1/watermarked")
        assert resp.status_code == 401
