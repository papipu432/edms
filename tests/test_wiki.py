import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.services.wiki import WikiService


# --- WikiService Unit Tests ---


class TestWikiInitialization:
    def test_creates_directory_structure(self, tmp_path: Path):
        """Test that WikiService creates the required directory structure."""
        wiki_path = tmp_path / "wiki"
        WikiService(wiki_path=str(wiki_path))

        assert wiki_path.exists()
        assert (wiki_path / "entities").is_dir()
        assert (wiki_path / "topics").is_dir()
        assert (wiki_path / "summaries").is_dir()
        assert (wiki_path / "index.md").is_file()
        assert (wiki_path / "log.md").is_file()

    def test_does_not_overwrite_existing_files(self, tmp_path: Path):
        """Test that re-initializing does not overwrite existing files."""
        wiki_path = tmp_path / "wiki"
        wiki_path.mkdir(parents=True)
        index_path = wiki_path / "index.md"
        index_path.write_text("# Custom Index", encoding="utf-8")

        WikiService(wiki_path=str(wiki_path))

        # Should not overwrite existing index.md
        assert index_path.read_text(encoding="utf-8") == "# Custom Index"


class TestWikiIngest:
    def test_creates_summary_file(self, tmp_path: Path):
        """Test that ingest creates a summary file for the document."""
        wiki_path = tmp_path / "wiki"

        with patch("app.services.wiki.get_llm_client", return_value=None):
            service = WikiService(wiki_path=str(wiki_path))
            service.ingest(
                doc_id=1,
                title="Test Document",
                markdown_content="This is test content about Python programming.",
                summary="A document about Python.",
                keywords=["python", "programming"],
                metadata={"group_id": 1},
            )

        summary_path = wiki_path / "summaries" / "1.md"
        assert summary_path.exists()
        content = summary_path.read_text(encoding="utf-8")
        assert "Test Document" in content
        assert "A document about Python." in content
        assert "python, programming" in content

    def test_updates_index_md(self, tmp_path: Path):
        """Test that ingest updates the index.md file."""
        wiki_path = tmp_path / "wiki"

        with patch("app.services.wiki.get_llm_client", return_value=None):
            service = WikiService(wiki_path=str(wiki_path))
            service.ingest(
                doc_id=1,
                title="Test Document",
                markdown_content="Content here.",
                summary="Summary here.",
                keywords=["test"],
                metadata={},
            )

        index_content = (wiki_path / "index.md").read_text(encoding="utf-8")
        assert "[Test Document](summaries/1.md)" in index_content

    def test_updates_log_md(self, tmp_path: Path):
        """Test that ingest appends an entry to log.md."""
        wiki_path = tmp_path / "wiki"

        with patch("app.services.wiki.get_llm_client", return_value=None):
            service = WikiService(wiki_path=str(wiki_path))
            service.ingest(
                doc_id=1,
                title="Test Document",
                markdown_content="Content.",
                summary="Summary.",
                keywords=["test"],
                metadata={},
            )

        log_content = (wiki_path / "log.md").read_text(encoding="utf-8")
        assert "ingest" in log_content
        assert "doc_id=1" in log_content
        assert "Test Document" in log_content

    def test_creates_entity_and_topic_pages_with_llm(self, tmp_path: Path):
        """Test that ingest creates entity/topic pages when LLM returns results."""
        wiki_path = tmp_path / "wiki"

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({
            "entities": ["Python", "FastAPI"],
            "topics": ["Web Development"],
        })
        mock_client.chat.completions.create.return_value = mock_response

        with patch("app.services.wiki.get_llm_client", return_value=mock_client):
            service = WikiService(wiki_path=str(wiki_path))
            service.ingest(
                doc_id=1,
                title="Test Doc",
                markdown_content="Python and FastAPI for web development.",
                summary="A doc about Python and FastAPI.",
                keywords=["python", "fastapi"],
                metadata={},
            )

        assert (wiki_path / "entities" / "python.md").exists()
        assert (wiki_path / "entities" / "fastapi.md").exists()
        assert (wiki_path / "topics" / "web-development.md").exists()

        # Check index references
        index_content = (wiki_path / "index.md").read_text(encoding="utf-8")
        assert "[python](entities/python.md)" in index_content
        assert "[fastapi](entities/fastapi.md)" in index_content
        assert "[web-development](topics/web-development.md)" in index_content

    def test_merges_entity_page_on_second_ingest(self, tmp_path: Path):
        """Test that ingesting a second document merges info into existing entity pages."""
        wiki_path = tmp_path / "wiki"

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({
            "entities": ["Python"],
            "topics": [],
        })
        mock_client.chat.completions.create.return_value = mock_response

        with patch("app.services.wiki.get_llm_client", return_value=mock_client):
            service = WikiService(wiki_path=str(wiki_path))

            # First ingest
            service.ingest(
                doc_id=1,
                title="Doc One",
                markdown_content="Python basics.",
                summary="Basics of Python.",
                keywords=["python"],
                metadata={},
            )

            # For the merge call, return merged content
            merge_response = MagicMock()
            merge_response.choices = [MagicMock()]
            merge_response.choices[0].message.content = "# Python\n\nMerged content from Doc One and Doc Two."

            # Second call for extraction, third for merge
            mock_client.chat.completions.create.side_effect = [
                mock_response,  # extract entities/topics
                merge_response,  # merge page content
            ]

            # Second ingest
            service.ingest(
                doc_id=2,
                title="Doc Two",
                markdown_content="Advanced Python.",
                summary="Advanced Python topics.",
                keywords=["python", "advanced"],
                metadata={},
            )

        entity_content = (wiki_path / "entities" / "python.md").read_text(encoding="utf-8")
        assert "Merged content" in entity_content or "Python" in entity_content


class TestWikiQuery:
    def test_query_returns_answer(self, tmp_path: Path):
        """Test that query searches wiki and returns an LLM-generated answer."""
        wiki_path = tmp_path / "wiki"

        with patch("app.services.wiki.get_llm_client", return_value=None):
            service = WikiService(wiki_path=str(wiki_path))
            service.ingest(
                doc_id=1,
                title="Python Basics",
                markdown_content="Python is a programming language.",
                summary="About Python.",
                keywords=["python"],
                metadata={},
            )

        with patch("app.services.wiki.chat_completion", return_value="Python is a general-purpose programming language."):
            answer = service.query("What is Python?")

        assert "Python" in answer
        assert "programming language" in answer

    def test_query_with_no_api_key(self, tmp_path: Path):
        """Test that query works gracefully without API key."""
        wiki_path = tmp_path / "wiki"

        with patch("app.services.wiki.get_llm_client", return_value=None):
            service = WikiService(wiki_path=str(wiki_path))

        with patch("app.services.wiki.chat_completion", return_value="Chat is not available (no API key configured)"):
            answer = service.query("What is Python?")

        assert "not available" in answer


class TestWikiLint:
    def test_detects_orphan_pages(self, tmp_path: Path):
        """Test that lint detects pages not listed in index.md."""
        wiki_path = tmp_path / "wiki"

        with patch("app.services.wiki.get_llm_client", return_value=None):
            service = WikiService(wiki_path=str(wiki_path))

        # Create an orphan page (not in index.md)
        orphan_path = wiki_path / "entities" / "orphan-entity.md"
        orphan_path.write_text("# Orphan Entity\n\nThis is orphaned.", encoding="utf-8")

        issues = service.lint()
        assert len(issues) >= 1
        orphan_issues = [i for i in issues if i["type"] == "orphan_page"]
        assert any("orphan-entity.md" in i["detail"] for i in orphan_issues)

    def test_detects_broken_links(self, tmp_path: Path):
        """Test that lint detects broken markdown links."""
        wiki_path = tmp_path / "wiki"

        with patch("app.services.wiki.get_llm_client", return_value=None):
            service = WikiService(wiki_path=str(wiki_path))

        # Create a page with a broken link
        entity_path = wiki_path / "entities" / "test-entity.md"
        entity_path.write_text(
            "# Test\n\nSee [nonexistent](../topics/nonexistent.md)\n",
            encoding="utf-8",
        )

        issues = service.lint()
        broken_issues = [i for i in issues if i["type"] == "broken_link"]
        assert len(broken_issues) >= 1
        assert any("nonexistent" in i["detail"] for i in broken_issues)

    def test_clean_wiki_has_no_issues(self, tmp_path: Path):
        """Test that a properly structured wiki has no lint issues."""
        wiki_path = tmp_path / "wiki"

        with patch("app.services.wiki.get_llm_client", return_value=None):
            service = WikiService(wiki_path=str(wiki_path))

        # A fresh wiki with no extra files should have no issues
        issues = service.lint()
        assert issues == []


class TestWikiGetters:
    def test_get_index(self, tmp_path: Path):
        """Test get_index returns content and page list."""
        wiki_path = tmp_path / "wiki"

        with patch("app.services.wiki.get_llm_client", return_value=None):
            service = WikiService(wiki_path=str(wiki_path))
            service.ingest(
                doc_id=1,
                title="Test Doc",
                markdown_content="Content.",
                summary="Summary.",
                keywords=["test"],
                metadata={},
            )

        content, pages = service.get_index()
        assert "Wiki Index" in content
        assert "summaries/1.md" in pages

    def test_get_page(self, tmp_path: Path):
        """Test get_page returns page content."""
        wiki_path = tmp_path / "wiki"

        with patch("app.services.wiki.get_llm_client", return_value=None):
            service = WikiService(wiki_path=str(wiki_path))
            service.ingest(
                doc_id=1,
                title="Test Doc",
                markdown_content="Content.",
                summary="Summary.",
                keywords=["test"],
                metadata={},
            )

        content = service.get_page("summaries/1.md")
        assert content is not None
        assert "Test Doc" in content

    def test_get_page_not_found(self, tmp_path: Path):
        """Test get_page returns None for missing page."""
        wiki_path = tmp_path / "wiki"

        with patch("app.services.wiki.get_llm_client", return_value=None):
            service = WikiService(wiki_path=str(wiki_path))

        content = service.get_page("entities/nonexistent.md")
        assert content is None

    def test_get_page_path_traversal_blocked(self, tmp_path: Path):
        """Test get_page rejects path traversal attempts."""
        wiki_path = tmp_path / "wiki"

        with patch("app.services.wiki.get_llm_client", return_value=None):
            service = WikiService(wiki_path=str(wiki_path))

        # Create a .md file outside the wiki directory
        secret_file = tmp_path / "secret.md"
        secret_file.write_text("SECRET CONTENT", encoding="utf-8")

        # Attempt path traversal
        content = service.get_page("../secret.md")
        assert content is None

    def test_get_page_path_traversal_nested(self, tmp_path: Path):
        """Test get_page rejects nested path traversal attempts."""
        wiki_path = tmp_path / "wiki"

        with patch("app.services.wiki.get_llm_client", return_value=None):
            service = WikiService(wiki_path=str(wiki_path))

        # Create a .md file outside the wiki directory in a nested path
        other_dir = tmp_path / "other"
        other_dir.mkdir()
        secret_file = other_dir / "data.md"
        secret_file.write_text("SENSITIVE DATA", encoding="utf-8")

        # Attempt nested path traversal
        content = service.get_page("entities/../../other/data.md")
        assert content is None

    def test_get_log(self, tmp_path: Path):
        """Test get_log returns log entries."""
        wiki_path = tmp_path / "wiki"

        with patch("app.services.wiki.get_llm_client", return_value=None):
            service = WikiService(wiki_path=str(wiki_path))
            service.ingest(
                doc_id=1,
                title="Test Doc",
                markdown_content="Content.",
                summary="Summary.",
                keywords=["test"],
                metadata={},
            )

        entries = service.get_log()
        assert len(entries) == 1
        assert "ingest" in entries[0]
        assert "doc_id=1" in entries[0]


# --- API Endpoint Tests ---


@pytest_asyncio.fixture
async def wiki_client(tmp_path: Path):
    """Create a test client with a temporary wiki directory."""
    import app.api.wiki as wiki_module

    # Create a wiki service with tmp_path
    wiki_path = tmp_path / "wiki"

    with patch("app.services.wiki.get_llm_client", return_value=None):
        test_wiki_service = WikiService(wiki_path=str(wiki_path))

    # Override the module-level wiki_service
    original_service = wiki_module.wiki_service
    wiki_module.wiki_service = test_wiki_service

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac, test_wiki_service

    wiki_module.wiki_service = original_service


class TestWikiAPIEndpoints:
    @pytest.mark.asyncio
    async def test_get_index(self, wiki_client):
        """Test GET /api/wiki/index returns index content."""
        client, service = wiki_client

        response = await client.get("/api/wiki/index")
        assert response.status_code == 200
        data = response.json()
        assert "content" in data
        assert "pages" in data
        assert "Wiki Index" in data["content"]

    @pytest.mark.asyncio
    async def test_get_page(self, wiki_client):
        """Test GET /api/wiki/pages/{path} returns page content."""
        client, service = wiki_client

        # Ingest a document to create a page
        with patch("app.services.wiki.get_llm_client", return_value=None):
            service.ingest(
                doc_id=1,
                title="API Test Doc",
                markdown_content="Content for API test.",
                summary="API test summary.",
                keywords=["api"],
                metadata={},
            )

        response = await client.get("/api/wiki/pages/summaries/1.md")
        assert response.status_code == 200
        data = response.json()
        assert data["path"] == "summaries/1.md"
        assert "API Test Doc" in data["content"]

    @pytest.mark.asyncio
    async def test_get_page_not_found(self, wiki_client):
        """Test GET /api/wiki/pages/{path} returns 404 for missing page."""
        client, service = wiki_client

        response = await client.get("/api/wiki/pages/entities/nonexistent.md")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_query_wiki(self, wiki_client):
        """Test POST /api/wiki/query returns an answer."""
        client, service = wiki_client

        with patch("app.services.wiki.get_llm_client", return_value=None):
            service.ingest(
                doc_id=1,
                title="Python Guide",
                markdown_content="Python is a versatile language.",
                summary="Guide to Python.",
                keywords=["python"],
                metadata={},
            )

        with patch("app.services.wiki.chat_completion", return_value="Python is versatile."):
            response = await client.post(
                "/api/wiki/query",
                json={"question": "What is Python?"},
            )

        assert response.status_code == 200
        data = response.json()
        assert "answer" in data
        assert "Python" in data["answer"]
        assert "sources" in data

    @pytest.mark.asyncio
    async def test_lint_wiki(self, wiki_client):
        """Test POST /api/wiki/lint returns issues."""
        client, service = wiki_client

        # Create an orphan page
        wiki_path = Path(service.wiki_path)
        orphan = wiki_path / "entities" / "orphan.md"
        orphan.write_text("# Orphan\n", encoding="utf-8")

        response = await client.post("/api/wiki/lint")
        assert response.status_code == 200
        data = response.json()
        assert "issues" in data
        assert len(data["issues"]) >= 1
        assert any(i["type"] == "orphan_page" for i in data["issues"])

    @pytest.mark.asyncio
    async def test_get_log(self, wiki_client):
        """Test GET /api/wiki/log returns log entries."""
        client, service = wiki_client

        with patch("app.services.wiki.get_llm_client", return_value=None):
            service.ingest(
                doc_id=1,
                title="Log Test",
                markdown_content="Content.",
                summary="Summary.",
                keywords=["test"],
                metadata={},
            )

        response = await client.get("/api/wiki/log")
        assert response.status_code == 200
        data = response.json()
        assert "entries" in data
        assert len(data["entries"]) >= 1
        assert "ingest" in data["entries"][0]
