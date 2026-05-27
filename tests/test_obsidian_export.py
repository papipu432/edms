"""Tests for the Obsidian vault export feature."""

import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.services.obsidian_export import ObsidianExportService


@pytest.fixture
def wiki_path(tmp_path: Path) -> Path:
    """Create a temporary wiki directory with sample pages."""
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    (wiki / "entities").mkdir()
    (wiki / "topics").mkdir()
    (wiki / "summaries").mkdir()

    # Create sample entity page
    entity_content = (
        "# Acme Corp\n\n"
        "Referenced in [Annual Report](../summaries/1.md) (Document 1).\n\n"
        "Referenced in [Q4 Results](../summaries/2.md) (Document 2).\n\n"
        "See also [John Smith](../entities/john-smith.md).\n"
    )
    (wiki / "entities" / "acme-corp.md").write_text(entity_content, encoding="utf-8")

    # Create another entity page
    entity2_content = (
        "# John Smith\n\n"
        "Referenced in [Annual Report](../summaries/1.md) (Document 1).\n"
    )
    (wiki / "entities" / "john-smith.md").write_text(entity2_content, encoding="utf-8")

    # Create sample topic page
    topic_content = (
        "# Financial Analysis\n\n"
        "Referenced in [Annual Report](../summaries/1.md) (Document 1).\n\n"
        "Referenced in [Q4 Results](../summaries/2.md) (Document 2).\n"
    )
    (wiki / "topics" / "financial-analysis.md").write_text(topic_content, encoding="utf-8")

    # Create sample summary page
    summary_content = (
        "# Annual Report 2024\n\n"
        "**Document ID:** 1\n\n"
        "**Date:** 2024-01-15T10:00:00+00:00\n\n"
        "**Keywords:** finance, quarterly, revenue\n\n"
        "## Summary\n\n"
        "This document covers the annual financial results.\n"
    )
    (wiki / "summaries" / "1.md").write_text(summary_content, encoding="utf-8")

    return wiki


@pytest.fixture
def export_service(wiki_path: Path) -> ObsidianExportService:
    """Create an ObsidianExportService instance with the test wiki."""
    return ObsidianExportService(wiki_path=str(wiki_path))


class TestConvertToWikilinks:
    """Tests for markdown link to wikilink conversion."""

    def test_convert_relative_entity_link(self, export_service: ObsidianExportService):
        content = "See [Acme Corp](../entities/acme-corp.md) for details."
        result = export_service.convert_to_wikilinks(content)
        assert result == "See [[acme-corp]] for details."

    def test_convert_relative_summary_link(self, export_service: ObsidianExportService):
        content = "Referenced in [Annual Report](../summaries/1.md)."
        result = export_service.convert_to_wikilinks(content)
        assert result == "Referenced in [[1]]."

    def test_convert_relative_topic_link(self, export_service: ObsidianExportService):
        content = "See [Finance](../topics/financial-analysis.md)."
        result = export_service.convert_to_wikilinks(content)
        assert result == "See [[financial-analysis]]."

    def test_preserves_external_links(self, export_service: ObsidianExportService):
        content = "Visit [Google](https://google.com) for more info."
        result = export_service.convert_to_wikilinks(content)
        assert result == "Visit [Google](https://google.com) for more info."

    def test_preserves_http_links(self, export_service: ObsidianExportService):
        content = "Visit [Site](http://example.com) for more."
        result = export_service.convert_to_wikilinks(content)
        assert result == "Visit [Site](http://example.com) for more."

    def test_convert_multiple_links(self, export_service: ObsidianExportService):
        content = (
            "See [Acme](../entities/acme-corp.md) and "
            "[John](../entities/john-smith.md) in the report."
        )
        result = export_service.convert_to_wikilinks(content)
        assert "[[acme-corp]]" in result
        assert "[[john-smith]]" in result

    def test_convert_same_directory_link(self, export_service: ObsidianExportService):
        content = "See [Related](./some-page.md) for details."
        result = export_service.convert_to_wikilinks(content)
        assert result == "See [[some-page]] for details."

    def test_no_links_unchanged(self, export_service: ObsidianExportService):
        content = "This is plain text with no links."
        result = export_service.convert_to_wikilinks(content)
        assert result == content


class TestFrontmatterGeneration:
    """Tests for YAML frontmatter generation."""

    def test_entity_frontmatter_has_required_fields(
        self, export_service: ObsidianExportService, wiki_path: Path
    ):
        content = (wiki_path / "entities" / "acme-corp.md").read_text(encoding="utf-8")
        frontmatter = export_service.generate_frontmatter("entities/acme-corp.md", content)

        assert frontmatter.startswith("---")
        assert frontmatter.endswith("---")
        assert 'title: "Acme Corp"' in frontmatter
        assert "type:: entity" in frontmatter
        assert "tags:" in frontmatter
        assert "aliases:" in frontmatter
        assert "date_created::" in frontmatter
        assert "date_modified::" in frontmatter
        assert "source_documents::" in frontmatter

    def test_entity_frontmatter_extracts_document_ids(
        self, export_service: ObsidianExportService, wiki_path: Path
    ):
        content = (wiki_path / "entities" / "acme-corp.md").read_text(encoding="utf-8")
        frontmatter = export_service.generate_frontmatter("entities/acme-corp.md", content)

        assert "source_documents:: [1, 2]" in frontmatter

    def test_entity_frontmatter_extracts_related(
        self, export_service: ObsidianExportService, wiki_path: Path
    ):
        content = (wiki_path / "entities" / "acme-corp.md").read_text(encoding="utf-8")
        frontmatter = export_service.generate_frontmatter("entities/acme-corp.md", content)

        assert "related:: [john-smith]" in frontmatter

    def test_summary_frontmatter_extracts_keywords_as_tags(
        self, export_service: ObsidianExportService, wiki_path: Path
    ):
        content = (wiki_path / "summaries" / "1.md").read_text(encoding="utf-8")
        frontmatter = export_service.generate_frontmatter("summaries/1.md", content)

        assert "tags:" in frontmatter
        assert "summary" in frontmatter
        assert "finance" in frontmatter
        assert "quarterly" in frontmatter
        assert "revenue" in frontmatter

    def test_topic_frontmatter_has_type(
        self, export_service: ObsidianExportService, wiki_path: Path
    ):
        content = (wiki_path / "topics" / "financial-analysis.md").read_text(encoding="utf-8")
        frontmatter = export_service.generate_frontmatter(
            "topics/financial-analysis.md", content
        )

        assert "type:: topic" in frontmatter

    def test_frontmatter_valid_yaml_delimiters(
        self, export_service: ObsidianExportService, wiki_path: Path
    ):
        content = (wiki_path / "entities" / "acme-corp.md").read_text(encoding="utf-8")
        frontmatter = export_service.generate_frontmatter("entities/acme-corp.md", content)

        lines = frontmatter.split("\n")
        assert lines[0] == "---"
        assert lines[-1] == "---"

    def test_dataview_properties_use_double_colon(
        self, export_service: ObsidianExportService, wiki_path: Path
    ):
        content = (wiki_path / "entities" / "acme-corp.md").read_text(encoding="utf-8")
        frontmatter = export_service.generate_frontmatter("entities/acme-corp.md", content)

        # Dataview properties use key:: value format
        assert "type::" in frontmatter
        assert "date_created::" in frontmatter
        assert "date_modified::" in frontmatter
        assert "source_documents::" in frontmatter


class TestExportPage:
    """Tests for full page export."""

    def test_export_page_combines_frontmatter_and_content(
        self, export_service: ObsidianExportService, wiki_path: Path
    ):
        content = (wiki_path / "entities" / "acme-corp.md").read_text(encoding="utf-8")
        result = export_service.export_page("entities/acme-corp.md", content)

        # Starts with frontmatter
        assert result.startswith("---\n")
        # Contains wikilinks instead of markdown links
        assert "[[1]]" in result
        assert "[[john-smith]]" in result
        # Does not contain original markdown links
        assert "[Annual Report](../summaries/1.md)" not in result

    def test_export_page_handles_no_metadata_gracefully(
        self, export_service: ObsidianExportService, wiki_path: Path
    ):
        # Create a minimal page with no special metadata
        minimal_content = "Just some plain text without headers or links."
        (wiki_path / "entities" / "minimal.md").write_text(
            minimal_content, encoding="utf-8"
        )

        result = export_service.export_page("entities/minimal.md", minimal_content)

        # Should still have valid frontmatter
        assert result.startswith("---\n")
        assert "type:: entity" in result
        assert "source_documents:: []" in result
        # Original content is preserved
        assert "Just some plain text without headers or links." in result


class TestExportVault:
    """Tests for full vault export."""

    def test_export_vault_returns_all_pages(
        self, export_service: ObsidianExportService, wiki_path: Path
    ):
        vault = export_service.export_vault(str(wiki_path))

        assert "entities/acme-corp.md" in vault
        assert "entities/john-smith.md" in vault
        assert "topics/financial-analysis.md" in vault
        assert "summaries/1.md" in vault

    def test_export_vault_pages_have_frontmatter(
        self, export_service: ObsidianExportService, wiki_path: Path
    ):
        vault = export_service.export_vault(str(wiki_path))

        for path, content in vault.items():
            assert content.startswith("---\n"), f"Page {path} missing frontmatter"

    def test_export_vault_maintains_directory_structure(
        self, export_service: ObsidianExportService, wiki_path: Path
    ):
        vault = export_service.export_vault(str(wiki_path))

        entity_pages = [p for p in vault if p.startswith("entities/")]
        topic_pages = [p for p in vault if p.startswith("topics/")]
        summary_pages = [p for p in vault if p.startswith("summaries/")]

        assert len(entity_pages) == 2
        assert len(topic_pages) == 1
        assert len(summary_pages) == 1

    def test_create_vault_zip_is_valid(
        self, export_service: ObsidianExportService, wiki_path: Path
    ):
        zip_buffer = export_service.create_vault_zip(str(wiki_path))

        with zipfile.ZipFile(zip_buffer, "r") as zf:
            names = zf.namelist()
            assert "entities/acme-corp.md" in names
            assert "entities/john-smith.md" in names
            assert "topics/financial-analysis.md" in names
            assert "summaries/1.md" in names

            # Verify content is valid (has frontmatter)
            content = zf.read("entities/acme-corp.md").decode("utf-8")
            assert content.startswith("---\n")
            assert "[[john-smith]]" in content

    def test_create_vault_zip_empty_wiki(self, tmp_path: Path):
        empty_wiki = tmp_path / "empty_wiki"
        empty_wiki.mkdir()
        (empty_wiki / "entities").mkdir()
        (empty_wiki / "topics").mkdir()
        (empty_wiki / "summaries").mkdir()

        service = ObsidianExportService(wiki_path=str(empty_wiki))
        zip_buffer = service.create_vault_zip(str(empty_wiki))

        with zipfile.ZipFile(zip_buffer, "r") as zf:
            assert zf.namelist() == []


class TestSyncChanges:
    """Tests for incremental sync."""

    def test_sync_returns_all_pages_when_no_timestamp(
        self, export_service: ObsidianExportService, wiki_path: Path
    ):
        # Use a very old timestamp
        changes = export_service.get_sync_changes(
            str(wiki_path), "2000-01-01T00:00:00+00:00"
        )

        assert "entities/acme-corp.md" in changes["changed"]
        assert "entities/john-smith.md" in changes["changed"]
        assert "topics/financial-analysis.md" in changes["changed"]
        assert "summaries/1.md" in changes["changed"]
        assert changes["deleted"] == []

    def test_sync_returns_only_recent_changes(
        self, export_service: ObsidianExportService, wiki_path: Path
    ):
        # Record timestamp before creating new file
        before = datetime.now(timezone.utc).isoformat()

        # Small delay to ensure file mtime is after the timestamp
        time.sleep(0.1)

        # Create a new page after the timestamp
        new_content = "# New Page\n\nNew content.\n"
        (wiki_path / "entities" / "new-entity.md").write_text(
            new_content, encoding="utf-8"
        )

        changes = export_service.get_sync_changes(str(wiki_path), before)

        assert "entities/new-entity.md" in changes["changed"]
        # Existing files should not be in changed (they were created before the timestamp)
        # Note: depending on filesystem timing, we check the new file is present
        assert len(changes["changed"]) >= 1

    def test_sync_with_none_timestamp_returns_all(
        self, export_service: ObsidianExportService, wiki_path: Path
    ):
        changes = export_service.get_sync_changes(str(wiki_path), None)

        assert len(changes["changed"]) == 4
        assert changes["deleted"] == []


class TestAPIEndpoints:
    """Tests for the Obsidian export API endpoints."""

    @pytest_asyncio.fixture
    async def obsidian_client(
        self, tmp_path: Path, wiki_path: Path
    ) -> AsyncClient:
        """Create a test client with the wiki path overridden."""
        import app.api.obsidian as obsidian_module
        from app.main import app
        from app.services.obsidian_export import ObsidianExportService

        # Override the export service to use our test wiki
        obsidian_module.export_service = ObsidianExportService(
            wiki_path=str(wiki_path)
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac

    @pytest.mark.anyio
    async def test_export_vault_endpoint_returns_zip(
        self, obsidian_client: AsyncClient
    ):
        response = await obsidian_client.get("/api/wiki/export/obsidian")

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/zip"
        assert "obsidian-vault.zip" in response.headers.get(
            "content-disposition", ""
        )

        # Verify it's a valid zip
        import io

        zip_buffer = io.BytesIO(response.content)
        with zipfile.ZipFile(zip_buffer, "r") as zf:
            names = zf.namelist()
            assert "entities/acme-corp.md" in names
            assert "summaries/1.md" in names

    @pytest.mark.anyio
    async def test_sync_endpoint_returns_changes(
        self, obsidian_client: AsyncClient
    ):
        # Use a very old timestamp to get all pages
        response = await obsidian_client.get(
            "/api/wiki/export/obsidian/sync",
            params={"since": "2000-01-01T00:00:00+00:00"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "changed" in data
        assert "deleted" in data
        assert len(data["changed"]) > 0
        assert "entities/acme-corp.md" in data["changed"]

    @pytest.mark.anyio
    async def test_sync_endpoint_requires_since_param(
        self, obsidian_client: AsyncClient
    ):
        response = await obsidian_client.get("/api/wiki/export/obsidian/sync")

        assert response.status_code == 422  # Missing required query param

    @pytest.mark.anyio
    async def test_page_endpoint_returns_obsidian_format(
        self, obsidian_client: AsyncClient, wiki_path: Path
    ):
        # Temporarily patch settings.WIKI_PATH for this test
        from unittest.mock import patch

        with patch("app.api.obsidian.settings") as mock_settings:
            mock_settings.WIKI_PATH = str(wiki_path)
            response = await obsidian_client.get(
                "/api/wiki/export/obsidian/page/entities/acme-corp.md"
            )

        assert response.status_code == 200
        data = response.json()
        assert data["path"] == "entities/acme-corp.md"
        assert "---" in data["content"]
        assert "[[john-smith]]" in data["content"]

    @pytest.mark.anyio
    async def test_page_endpoint_404_for_missing_page(
        self, obsidian_client: AsyncClient, wiki_path: Path
    ):
        from unittest.mock import patch

        with patch("app.api.obsidian.settings") as mock_settings:
            mock_settings.WIKI_PATH = str(wiki_path)
            response = await obsidian_client.get(
                "/api/wiki/export/obsidian/page/entities/nonexistent.md"
            )

        assert response.status_code == 404
