import io
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select

from app.core.security import create_access_token, hash_password
from app.models.document import Document, DocumentStatus
from app.models.group import Group
from app.models.user import Role, User, UserRole
from app.services.preview import PreviewService


@pytest.fixture
def preview_service():
    return PreviewService()


@pytest.fixture
def test_pdf(tmp_path: Path) -> Path:
    """Create a simple PDF using PyMuPDF for testing."""
    import fitz

    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Hello, preview test!")
    pdf_path = tmp_path / "test.pdf"
    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


@pytest.fixture
def test_image(tmp_path: Path) -> Path:
    """Create a test PNG image using Pillow."""
    from PIL import Image

    img = Image.new("RGB", (800, 600), color=(255, 0, 0))
    img_path = tmp_path / "test.png"
    img.save(img_path)
    return img_path


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
        username="previewuser",
        email="preview@edms.local",
        display_name="Preview User",
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
    group = Group(name="Preview Test Group", description="For preview tests")
    seeded_db.add(group)
    await seeded_db.flush()
    await seeded_db.refresh(group)
    return group


class TestPreviewService:
    def test_pdf_preview_generates_valid_png(self, preview_service: PreviewService, test_pdf: Path):
        """PDF preview generates valid PNG bytes."""
        result = preview_service.generate_pdf_preview(test_pdf)
        assert result is not None
        # Check PNG magic bytes
        assert result[:8] == b"\x89PNG\r\n\x1a\n"

    def test_pdf_preview_returns_none_for_invalid_file(self, preview_service: PreviewService, tmp_path: Path):
        """PDF preview returns None for invalid file."""
        bad_file = tmp_path / "bad.pdf"
        bad_file.write_text("not a pdf")
        result = preview_service.generate_pdf_preview(bad_file)
        assert result is None

    def test_markdown_preview_generates_html(self, preview_service: PreviewService):
        """Markdown preview generates HTML with proper tags."""
        md_content = "# Title\n\nSome **bold** and *italic* text.\n\n- Item 1\n- Item 2\n"
        result = preview_service.generate_markdown_preview(md_content)
        assert "<h1>" in result
        assert "<strong>bold</strong>" in result
        assert "<em>italic</em>" in result
        assert "<li>" in result
        assert "<!DOCTYPE html>" in result

    def test_markdown_preview_limits_content(self, preview_service: PreviewService):
        """Preview content is limited and doesn't expose full document."""
        long_content = "# Document\n\n" + "A" * 5000
        result = preview_service.generate_markdown_preview(long_content, max_chars=100)
        # Should not contain the full 5000 characters
        assert "A" * 5000 not in result

    def test_markdown_preview_handles_code(self, preview_service: PreviewService):
        """Markdown preview handles inline code."""
        md_content = "Use `print()` function"
        result = preview_service.generate_markdown_preview(md_content)
        assert "<code>print()</code>" in result

    def test_image_preview_generates_thumbnail_png(self, preview_service: PreviewService, test_image: Path):
        """Image preview generates a thumbnail PNG."""
        result = preview_service.generate_image_preview(test_image)
        assert result is not None
        # Check PNG magic bytes
        assert result[:8] == b"\x89PNG\r\n\x1a\n"
        # Verify it's a thumbnail (smaller than original)
        from PIL import Image

        thumb = Image.open(io.BytesIO(result))
        assert thumb.width <= 400
        assert thumb.height <= 400

    def test_image_preview_returns_none_for_invalid(self, preview_service: PreviewService, tmp_path: Path):
        """Image preview returns None for invalid file."""
        bad_file = tmp_path / "bad.png"
        bad_file.write_text("not an image")
        result = preview_service.generate_image_preview(bad_file)
        assert result is None

    def test_get_preview_path(self, preview_service: PreviewService):
        """Preview path follows convention."""
        path = preview_service.get_preview_path(42)
        assert path == Path("data/previews/42_preview.png")

    def test_get_html_preview_path(self, preview_service: PreviewService):
        """HTML preview path follows convention."""
        path = preview_service.get_html_preview_path(42)
        assert path == Path("data/previews/42_preview.html")

    def test_generate_and_cache_pdf(self, preview_service: PreviewService, test_pdf: Path, tmp_path: Path, monkeypatch):
        """generate_and_cache creates PNG for PDF files."""
        monkeypatch.chdir(tmp_path)
        result = preview_service.generate_and_cache(1, test_pdf, "application/pdf")
        assert result is not None
        assert result.endswith(".png")
        assert Path(result).exists()

    def test_generate_and_cache_image(self, preview_service: PreviewService, test_image: Path, tmp_path: Path, monkeypatch):
        """generate_and_cache creates PNG thumbnail for images."""
        monkeypatch.chdir(tmp_path)
        result = preview_service.generate_and_cache(2, test_image, "image/png")
        assert result is not None
        assert result.endswith(".png")
        assert Path(result).exists()

    def test_generate_and_cache_markdown(self, preview_service: PreviewService, tmp_path: Path, monkeypatch):
        """generate_and_cache creates HTML for markdown content."""
        monkeypatch.chdir(tmp_path)
        result = preview_service.generate_and_cache(
            3, Path("nonexistent.txt"), "text/plain", markdown_content="# Hello\nWorld"
        )
        assert result is not None
        assert result.endswith(".html")
        assert Path(result).exists()

    def test_generate_and_cache_returns_none_on_failure(self, preview_service: PreviewService, tmp_path: Path, monkeypatch):
        """generate_and_cache returns None when generation fails."""
        monkeypatch.chdir(tmp_path)
        result = preview_service.generate_and_cache(
            99, Path("nonexistent.pdf"), "application/pdf"
        )
        assert result is None


class TestPreviewAPI:
    @pytest_asyncio.fixture
    async def doc_with_preview(self, seeded_db, test_group, test_user) -> Document:
        """Create a document and write a cached preview file."""
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

        # Write a preview file at the conventional path
        preview_path = Path(f"data/previews/{doc.id}_preview.png")
        preview_path.parent.mkdir(parents=True, exist_ok=True)
        # Minimal PNG using Pillow
        from PIL import Image

        img = Image.new("RGB", (100, 100), color=(0, 0, 255))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        preview_path.write_bytes(buf.getvalue())

        return doc

    @pytest_asyncio.fixture
    async def doc_without_preview(self, seeded_db, test_group, test_user) -> Document:
        """Create a document without a cached preview."""
        doc = Document(
            group_id=test_group.id,
            original_filename="no_preview.txt",
            storage_path="/tmp/no_preview.txt",
            file_type="text/plain",
            file_size=100,
            status=DocumentStatus.uploaded,
        )
        seeded_db.add(doc)
        await seeded_db.flush()
        await seeded_db.refresh(doc)

        # Ensure no leftover preview files exist for this doc
        preview_path = Path(f"data/previews/{doc.id}_preview.png")
        if preview_path.exists():
            preview_path.unlink()
        html_path = Path(f"data/previews/{doc.id}_preview.html")
        if html_path.exists():
            html_path.unlink()

        return doc

    @pytest.mark.asyncio
    async def test_get_preview_returns_cached_png(
        self, client: AsyncClient, doc_with_preview: Document, auth_token: str
    ):
        """GET /api/documents/{id}/preview returns cached preview."""
        resp = await client.get(
            f"/api/documents/{doc_with_preview.id}/preview",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/png"
        # Verify PNG magic bytes
        assert resp.content[:8] == b"\x89PNG\r\n\x1a\n"

    @pytest.mark.asyncio
    async def test_get_preview_404_nonexistent_document(
        self, client: AsyncClient, auth_token: str, test_user
    ):
        """Returns 404 for non-existent document."""
        resp = await client.get(
            "/api/documents/99999/preview",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_get_preview_404_no_preview_available(
        self, client: AsyncClient, doc_without_preview: Document, auth_token: str
    ):
        """Returns 404 when no preview is available (unprocessed doc)."""
        resp = await client.get(
            f"/api/documents/{doc_without_preview.id}/preview",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_get_preview_metadata_exists(
        self, client: AsyncClient, doc_with_preview: Document, auth_token: str
    ):
        """Preview metadata returns info about existing preview."""
        resp = await client.get(
            f"/api/documents/{doc_with_preview.id}/preview/metadata",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["document_id"] == doc_with_preview.id
        assert data["preview_type"] == "png"
        assert data["exists"] is True
        assert data["file_size"] > 0

    @pytest.mark.asyncio
    async def test_get_preview_metadata_not_exists(
        self, client: AsyncClient, doc_without_preview: Document, auth_token: str
    ):
        """Preview metadata returns exists=False when no preview."""
        resp = await client.get(
            f"/api/documents/{doc_without_preview.id}/preview/metadata",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["exists"] is False
        assert data["file_size"] == 0

    @pytest.mark.asyncio
    async def test_preview_requires_auth(self, client: AsyncClient, doc_with_preview: Document):
        """Preview endpoint requires authentication."""
        resp = await client.get(
            f"/api/documents/{doc_with_preview.id}/preview",
        )
        assert resp.status_code in (401, 403)
