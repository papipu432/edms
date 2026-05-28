from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select

from app.core.security import create_access_token, hash_password
from app.models.document import Document, DocumentStatus
from app.models.group import Group
from app.models.user import Role, User, UserRole
from app.services.converter import ConversionService


@pytest_asyncio.fixture
async def seeded_db(db_session):
    """Seed roles into the test database."""
    roles_data = [
        ("admin", "Administrator"),
        ("editor", "Editor"),
    ]
    for code, name in roles_data:
        db_session.add(Role(code=code, name=name, description=f"{code} role", is_system=True))
    await db_session.flush()
    return db_session


@pytest_asyncio.fixture
async def test_user(seeded_db):
    """Create a test user."""
    result = await seeded_db.execute(select(Role).where(Role.code == "admin"))
    admin_role = result.scalar_one()

    user = User(
        username="ocruser",
        email="ocr@edms.local",
        display_name="OCR User",
        hashed_password=hash_password("password"),
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
async def auth_token(test_user):
    """Create a valid JWT token for the test user."""
    return create_access_token(data={"sub": test_user.username})


@pytest_asyncio.fixture
async def test_group(seeded_db):
    """Create a test group."""
    group = Group(name="OCR Test Group", description="For OCR tests")
    seeded_db.add(group)
    await seeded_db.flush()
    await seeded_db.refresh(group)
    return group


@pytest_asyncio.fixture
async def doc_with_high_confidence(seeded_db, test_group, tmp_path):
    """Create a document with high OCR confidence."""
    doc = Document(
        group_id=test_group.id,
        original_filename="clear_scan.png",
        storage_path=str(tmp_path / "clear.png"),
        file_type="image/png",
        file_size=5000,
        status=DocumentStatus.processed,
        ocr_confidence=92.5,
    )
    seeded_db.add(doc)
    await seeded_db.flush()
    await seeded_db.refresh(doc)
    return doc


@pytest_asyncio.fixture
async def doc_with_low_confidence(seeded_db, test_group, tmp_path):
    """Create a document with low OCR confidence."""
    doc = Document(
        group_id=test_group.id,
        original_filename="blurry_scan.png",
        storage_path=str(tmp_path / "blurry.png"),
        file_type="image/png",
        file_size=3000,
        status=DocumentStatus.processed,
        ocr_confidence=45.2,
    )
    seeded_db.add(doc)
    await seeded_db.flush()
    await seeded_db.refresh(doc)
    return doc


@pytest_asyncio.fixture
async def doc_without_ocr(seeded_db, test_group, tmp_path):
    """Create a document without OCR confidence."""
    doc = Document(
        group_id=test_group.id,
        original_filename="native_text.pdf",
        storage_path=str(tmp_path / "native.pdf"),
        file_type="application/pdf",
        file_size=2000,
        status=DocumentStatus.processed,
        ocr_confidence=None,
    )
    seeded_db.add(doc)
    await seeded_db.flush()
    await seeded_db.refresh(doc)
    return doc


class TestOCRConfidenceConverter:
    """Unit tests for OCR confidence extraction in converter."""

    def test_convert_image_with_confidence(self, tmp_path):
        """Test that convert_image captures OCR confidence."""
        import pandas as pd
        from PIL import Image

        img = Image.new("RGB", (100, 30), color="white")
        img_path = tmp_path / "test.png"
        img.save(img_path)

        mock_df = pd.DataFrame({
            "conf": [95.0, 88.0, 72.0, -1, 90.0],
            "text": ["hello", "world", "test", "", "ok"],
        })

        with patch("pytesseract.image_to_data", return_value=mock_df):
            with patch("pytesseract.image_to_string", return_value="hello world test ok"):
                with patch("pytesseract.Output") as mock_output:
                    mock_output.DATAFRAME = "dataframe"
                    service = ConversionService()
                    result = service.convert_image(img_path)

        assert "ocr_confidence" in result.metadata
        expected_avg = (95.0 + 88.0 + 72.0 + 90.0) / 4
        assert abs(result.metadata["ocr_confidence"] - expected_avg) < 0.01

    def test_convert_image_without_tesseract(self, tmp_path):
        """Test graceful handling when tesseract is not available."""
        from PIL import Image

        img = Image.new("RGB", (100, 30), color="white")
        img_path = tmp_path / "test.png"
        img.save(img_path)

        with patch.dict("sys.modules", {"pytesseract": None}):
            service = ConversionService()
            with patch("builtins.__import__", side_effect=ImportError("No module")):
                result = service.convert_image(img_path)

        assert result.markdown_content == ""


@pytest.mark.asyncio
class TestOCRQualityAPI:
    """Integration tests for OCR quality API endpoint."""

    async def test_ocr_quality_requires_auth(self, client: AsyncClient):
        """Test that endpoint requires authentication."""
        resp = await client.get("/api/documents/1/ocr-quality")
        assert resp.status_code == 401

    async def test_ocr_quality_high_confidence(
        self, client: AsyncClient, auth_token, doc_with_high_confidence
    ):
        """Test OCR quality for high-confidence document."""
        resp = await client.get(
            f"/api/documents/{doc_with_high_confidence.id}/ocr-quality",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["document_id"] == doc_with_high_confidence.id
        assert data["ocr_confidence"] == 92.5
        assert data["needs_review"] is False

    async def test_ocr_quality_low_confidence(
        self, client: AsyncClient, auth_token, doc_with_low_confidence
    ):
        """Test OCR quality for low-confidence document needing review."""
        resp = await client.get(
            f"/api/documents/{doc_with_low_confidence.id}/ocr-quality",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["document_id"] == doc_with_low_confidence.id
        assert data["ocr_confidence"] == 45.2
        assert data["needs_review"] is True

    async def test_ocr_quality_no_confidence(
        self, client: AsyncClient, auth_token, doc_without_ocr
    ):
        """Test OCR quality when no OCR was performed."""
        resp = await client.get(
            f"/api/documents/{doc_without_ocr.id}/ocr-quality",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["document_id"] == doc_without_ocr.id
        assert data["ocr_confidence"] is None
        assert data["needs_review"] is False

    async def test_ocr_quality_nonexistent_document(
        self, client: AsyncClient, auth_token
    ):
        """Test OCR quality for non-existent document returns 404."""
        resp = await client.get(
            "/api/documents/99999/ocr-quality",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 404
