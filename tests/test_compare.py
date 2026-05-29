import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select

from app.core.security import create_access_token, hash_password
from app.models.document import Document, DocumentStatus
from app.models.group import Group
from app.models.user import Role, User, UserRole
from app.models.version import DocumentVersion
from app.services.comparison import ComparisonService


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
        username="compareuser",
        email="compare@edms.local",
        display_name="Compare User",
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
    group = Group(name="Compare Test Group", description="For compare tests")
    seeded_db.add(group)
    await seeded_db.flush()
    await seeded_db.refresh(group)
    return group


@pytest_asyncio.fixture
async def two_documents(seeded_db, test_group, tmp_path):
    """Create two documents with markdown content for comparison."""
    md_a = tmp_path / "doc_a.md"
    md_a.write_text("# Document A\n\nThis is paragraph one.\n\nShared content here.\n")

    md_b = tmp_path / "doc_b.md"
    md_b.write_text("# Document B\n\nThis is paragraph two.\n\nShared content here.\n\nExtra line.\n")

    doc_a = Document(
        group_id=test_group.id,
        original_filename="report_a.pdf",
        storage_path=str(tmp_path / "a.pdf"),
        file_type="application/pdf",
        file_size=1024,
        status=DocumentStatus.processed,
        summary="Summary of document A",
        keywords={"tags": ["alpha", "beta"]},
        markdown_path=str(md_a),
    )
    seeded_db.add(doc_a)
    await seeded_db.flush()
    await seeded_db.refresh(doc_a)

    doc_b = Document(
        group_id=test_group.id,
        original_filename="report_b.pdf",
        storage_path=str(tmp_path / "b.pdf"),
        file_type="application/pdf",
        file_size=2048,
        status=DocumentStatus.processed,
        summary="Summary of document B",
        keywords={"tags": ["gamma"]},
        markdown_path=str(md_b),
    )
    seeded_db.add(doc_b)
    await seeded_db.flush()
    await seeded_db.refresh(doc_b)

    return doc_a, doc_b


@pytest_asyncio.fixture
async def doc_without_markdown(seeded_db, test_group, tmp_path):
    """Create a document without markdown content."""
    doc = Document(
        group_id=test_group.id,
        original_filename="raw_file.txt",
        storage_path=str(tmp_path / "raw.txt"),
        file_type="text/plain",
        file_size=512,
        status=DocumentStatus.uploaded,
        summary=None,
        keywords=None,
        markdown_path=None,
    )
    seeded_db.add(doc)
    await seeded_db.flush()
    await seeded_db.refresh(doc)
    return doc


@pytest_asyncio.fixture
async def doc_with_versions(seeded_db, test_group, tmp_path):
    """Create a document with two versions having markdown content."""
    doc = Document(
        group_id=test_group.id,
        original_filename="versioned.pdf",
        storage_path=str(tmp_path / "versioned.pdf"),
        file_type="application/pdf",
        file_size=1000,
        status=DocumentStatus.processed,
        current_version=2,
    )
    seeded_db.add(doc)
    await seeded_db.flush()
    await seeded_db.refresh(doc)

    # Create version 1 markdown file
    v1_path = tmp_path / "versions" / "v1.md"
    v1_path.parent.mkdir(parents=True, exist_ok=True)
    v1_path.write_text("# Version 1\n\nOriginal content.\n")

    # Create version 2 markdown file
    v2_path = tmp_path / "versions" / "v2.md"
    v2_path.write_text("# Version 2\n\nUpdated content.\n\nNew section added.\n")

    version_1 = DocumentVersion(
        document_id=doc.id,
        version_number=1,
        storage_path=str(v1_path),
        file_size=500,
        file_type="application/pdf",
    )
    seeded_db.add(version_1)

    version_2 = DocumentVersion(
        document_id=doc.id,
        version_number=2,
        storage_path=str(v2_path),
        file_size=700,
        file_type="application/pdf",
    )
    seeded_db.add(version_2)
    await seeded_db.flush()

    return doc


class TestComparisonService:
    """Unit tests for ComparisonService."""

    def test_compare_metadata_identifies_differences(self, two_documents):
        """Metadata comparison correctly identifies differing fields."""
        # two_documents is a coroutine fixture, so we get the resolved value
        pass

    def test_compare_markdown_identical(self):
        """Identical content yields 0 additions, 0 deletions, ratio 1.0."""
        service = ComparisonService()
        content = "# Hello\n\nSame content.\n"
        result = service.compare_markdown_content(content, content)
        assert result["additions_count"] == 0
        assert result["deletions_count"] == 0
        assert result["similarity_ratio"] == 1.0
        assert result["unified_diff"] == ""

    def test_compare_markdown_completely_different(self):
        """Completely different content yields ratio close to 0.0."""
        service = ComparisonService()
        content_a = "alpha\nbeta\ngamma\n"
        content_b = "one\ntwo\nthree\nfour\n"
        result = service.compare_markdown_content(content_a, content_b)
        assert result["similarity_ratio"] < 0.5
        assert result["additions_count"] > 0
        assert result["deletions_count"] > 0

    def test_compare_markdown_additions_and_deletions(self):
        """Diff correctly counts additions and deletions."""
        service = ComparisonService()
        content_a = "line1\nline2\nline3\n"
        content_b = "line1\nline2_modified\nline3\nline4\n"
        result = service.compare_markdown_content(content_a, content_b)
        # line2 removed, line2_modified added, line4 added
        assert result["additions_count"] == 2
        assert result["deletions_count"] == 1

    def test_generate_diff_html_returns_html(self):
        """HTML diff returns valid HTML table content."""
        service = ComparisonService()
        content_a = "hello\nworld\n"
        content_b = "hello\nearth\n"
        html = service.generate_diff_html(content_a, content_b, "Doc A", "Doc B")
        assert "<table" in html
        assert "Doc A" in html
        assert "Doc B" in html

    def test_compare_versions_content_with_both_contents(self):
        """Version comparison includes content diff when both have content."""
        service = ComparisonService()
        result = service.compare_versions_content(
            content_a="line1\n",
            content_b="line2\n",
            meta_a={"version": 1},
            meta_b={"version": 2},
        )
        assert result["has_content_diff"] is True
        assert result["content_diff"] is not None
        assert result["content_diff"]["additions_count"] == 1
        assert result["content_diff"]["deletions_count"] == 1

    def test_compare_versions_content_without_content(self):
        """Version comparison without content returns no content diff."""
        service = ComparisonService()
        result = service.compare_versions_content(
            content_a=None,
            content_b="line2\n",
            meta_a={"version": 1},
            meta_b={"version": 2},
        )
        assert result["has_content_diff"] is False
        assert result["content_diff"] is None


@pytest.mark.asyncio
class TestCompareAPI:
    """Integration tests for compare API endpoints."""

    async def test_compare_documents_returns_metadata(
        self, client: AsyncClient, auth_token, two_documents
    ):
        """GET /api/documents/compare returns structured comparison data."""
        doc_a, doc_b = two_documents
        resp = await client.get(
            "/api/documents/compare",
            params={"doc_a": doc_a.id, "doc_b": doc_b.id},
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["metadata"] is not None
        fields = data["metadata"]["fields"]
        assert len(fields) > 0

        # Check that filename field differs
        filename_field = next(f for f in fields if f["field"] == "original_filename")
        assert filename_field["differs"] is True
        assert filename_field["doc_a_value"] == "report_a.pdf"
        assert filename_field["doc_b_value"] == "report_b.pdf"

    async def test_compare_documents_includes_content_diff(
        self, client: AsyncClient, auth_token, two_documents
    ):
        """Compare with markdown content returns content diff."""
        doc_a, doc_b = two_documents
        resp = await client.get(
            "/api/documents/compare",
            params={"doc_a": doc_a.id, "doc_b": doc_b.id},
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["has_content_diff"] is True
        assert data["content_diff"] is not None
        assert data["content_diff"]["additions_count"] > 0
        assert data["content_diff"]["deletions_count"] > 0
        assert 0.0 < data["content_diff"]["similarity_ratio"] < 1.0

    async def test_compare_nonexistent_document_returns_404(
        self, client: AsyncClient, auth_token, two_documents
    ):
        """Comparing non-existent documents returns 404."""
        doc_a, _ = two_documents
        resp = await client.get(
            "/api/documents/compare",
            params={"doc_a": doc_a.id, "doc_b": 99999},
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 404

    async def test_compare_without_markdown_returns_metadata_only(
        self, client: AsyncClient, auth_token, two_documents, doc_without_markdown
    ):
        """Comparing documents without markdown returns metadata only."""
        doc_a, _ = two_documents
        resp = await client.get(
            "/api/documents/compare",
            params={"doc_a": doc_a.id, "doc_b": doc_without_markdown.id},
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["metadata"] is not None
        assert data["has_content_diff"] is False
        assert data["content_diff"] is None

    async def test_compare_html_returns_html_content(
        self, client: AsyncClient, auth_token, two_documents
    ):
        """HTML comparison endpoint returns valid HTML."""
        doc_a, doc_b = two_documents
        resp = await client.get(
            "/api/documents/compare/html",
            params={"doc_a": doc_a.id, "doc_b": doc_b.id},
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        content = resp.text
        assert "<table" in content
        assert "Document Comparison" in content
        assert "report_a.pdf" in content
        assert "report_b.pdf" in content

    async def test_compare_html_without_markdown(
        self, client: AsyncClient, auth_token, two_documents, doc_without_markdown
    ):
        """HTML comparison without markdown shows metadata only."""
        doc_a, _ = two_documents
        resp = await client.get(
            "/api/documents/compare/html",
            params={"doc_a": doc_a.id, "doc_b": doc_without_markdown.id},
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 200
        assert "No markdown content available" in resp.text

    async def test_version_diff(
        self, client: AsyncClient, auth_token, doc_with_versions
    ):
        """Version diff returns content comparison between versions."""
        resp = await client.get(
            f"/api/documents/{doc_with_versions.id}/versions/diff",
            params={"version_a": 1, "version_b": 2},
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["additions_count"] > 0
        assert data["deletions_count"] > 0
        assert 0.0 < data["similarity_ratio"] < 1.0

    async def test_version_diff_nonexistent_version(
        self, client: AsyncClient, auth_token, doc_with_versions
    ):
        """Version diff with non-existent version returns 404."""
        resp = await client.get(
            f"/api/documents/{doc_with_versions.id}/versions/diff",
            params={"version_a": 1, "version_b": 99},
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 404

    async def test_version_diff_nonexistent_document(
        self, client: AsyncClient, auth_token
    ):
        """Version diff for non-existent document returns 404."""
        resp = await client.get(
            "/api/documents/99999/versions/diff",
            params={"version_a": 1, "version_b": 2},
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 404
