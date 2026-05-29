"""Tests for the Obsidian sync import feature."""

import json
import zipfile
from io import BytesIO
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.services.obsidian_sync import ObsidianSyncService


def _create_zip(files: dict[str, str]) -> bytes:
    """Helper to create a zip file in memory from a dict of path -> content."""
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for path, content in files.items():
            zf.writestr(path, content)
    return buf.getvalue()


@pytest.fixture
def wiki_path(tmp_path: Path) -> Path:
    """Create a temporary wiki directory with sample pages."""
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    (wiki / "entities").mkdir()
    (wiki / "topics").mkdir()
    (wiki / "summaries").mkdir()

    # Existing entity page
    (wiki / "entities" / "acme-corp.md").write_text(
        "# Acme Corp\n\nOriginal content.\n", encoding="utf-8"
    )

    # Existing topic page
    (wiki / "topics" / "finance.md").write_text(
        "# Finance\n\nOriginal topic content.\n", encoding="utf-8"
    )

    # Existing summary (EDMS-generated)
    (wiki / "summaries" / "1.md").write_text(
        "# Summary\n\nAuto-generated summary.\n", encoding="utf-8"
    )

    return wiki


@pytest.fixture
def sync_service(wiki_path: Path) -> ObsidianSyncService:
    """Create an ObsidianSyncService instance."""
    return ObsidianSyncService(wiki_path=str(wiki_path))


class TestImportNewPages:
    """Tests for importing new pages from Obsidian."""

    def test_import_new_entity_page(self, sync_service: ObsidianSyncService, wiki_path: Path):
        """New pages in zip that are not in wiki should be created."""
        zip_data = _create_zip({
            "entities/acme-corp.md": "# Acme Corp\n\nOriginal content.\n",
            "entities/new-entity.md": "# New Entity\n\nBrand new page.\n",
            "topics/finance.md": "# Finance\n\nOriginal topic content.\n",
            "summaries/1.md": "# Summary\n\nAuto-generated summary.\n",
        })

        result = sync_service.import_zip(zip_data)

        assert result.pages_created == 1
        assert (wiki_path / "entities" / "new-entity.md").exists()
        content = (wiki_path / "entities" / "new-entity.md").read_text(encoding="utf-8")
        assert "Brand new page" in content

    def test_import_multiple_new_pages(self, sync_service: ObsidianSyncService, wiki_path: Path):
        """Multiple new pages should all be created."""
        zip_data = _create_zip({
            "entities/acme-corp.md": "# Acme Corp\n\nOriginal content.\n",
            "entities/new-one.md": "# New One\n\nContent 1.\n",
            "topics/finance.md": "# Finance\n\nOriginal topic content.\n",
            "topics/new-topic.md": "# New Topic\n\nContent 2.\n",
            "summaries/1.md": "# Summary\n\nAuto-generated summary.\n",
        })

        result = sync_service.import_zip(zip_data)

        assert result.pages_created == 2


class TestImportModifiedPages:
    """Tests for importing modified pages from Obsidian."""

    def test_import_modified_entity_page(self, sync_service: ObsidianSyncService, wiki_path: Path):
        """Modified entity pages should be updated (Obsidian wins)."""
        zip_data = _create_zip({
            "entities/acme-corp.md": "# Acme Corp\n\nUpdated from Obsidian.\n",
            "topics/finance.md": "# Finance\n\nOriginal topic content.\n",
            "summaries/1.md": "# Summary\n\nAuto-generated summary.\n",
        })

        result = sync_service.import_zip(zip_data)

        assert result.pages_updated == 1
        content = (wiki_path / "entities" / "acme-corp.md").read_text(encoding="utf-8")
        assert "Updated from Obsidian" in content

    def test_import_modified_topic_page(self, sync_service: ObsidianSyncService, wiki_path: Path):
        """Modified topic pages should be updated (Obsidian wins)."""
        zip_data = _create_zip({
            "entities/acme-corp.md": "# Acme Corp\n\nOriginal content.\n",
            "topics/finance.md": "# Finance\n\nUpdated topic from Obsidian.\n",
            "summaries/1.md": "# Summary\n\nAuto-generated summary.\n",
        })

        result = sync_service.import_zip(zip_data)

        assert result.pages_updated == 1
        content = (wiki_path / "topics" / "finance.md").read_text(encoding="utf-8")
        assert "Updated topic from Obsidian" in content


class TestConflictResolution:
    """Tests for conflict resolution: summaries not overwritten."""

    def test_summary_not_overwritten(self, sync_service: ObsidianSyncService, wiki_path: Path):
        """Summaries should not be overwritten even if different in zip (EDMS wins)."""
        zip_data = _create_zip({
            "entities/acme-corp.md": "# Acme Corp\n\nOriginal content.\n",
            "topics/finance.md": "# Finance\n\nOriginal topic content.\n",
            "summaries/1.md": "# Summary\n\nModified by Obsidian user.\n",
        })

        result = sync_service.import_zip(zip_data)

        assert result.pages_updated == 0
        assert len(result.conflicts) == 1
        assert result.conflicts[0].path == "summaries/1.md"
        assert result.conflicts[0].resolution == "edms_wins"

        # Verify the original content is preserved
        content = (wiki_path / "summaries" / "1.md").read_text(encoding="utf-8")
        assert "Auto-generated summary" in content

    def test_entity_page_overwritten_on_conflict(
        self, sync_service: ObsidianSyncService, wiki_path: Path
    ):
        """Entity pages should be overwritten (Obsidian wins)."""
        zip_data = _create_zip({
            "entities/acme-corp.md": "# Acme Corp\n\nChanged by user in Obsidian.\n",
            "topics/finance.md": "# Finance\n\nOriginal topic content.\n",
            "summaries/1.md": "# Summary\n\nAuto-generated summary.\n",
        })

        result = sync_service.import_zip(zip_data)

        assert result.pages_updated == 1
        assert len(result.conflicts) == 0
        content = (wiki_path / "entities" / "acme-corp.md").read_text(encoding="utf-8")
        assert "Changed by user in Obsidian" in content


class TestSyncManifest:
    """Tests for sync manifest tracking."""

    def test_manifest_created_after_sync(self, sync_service: ObsidianSyncService, wiki_path: Path):
        """Sync manifest should be created after import."""
        zip_data = _create_zip({
            "entities/acme-corp.md": "# Acme Corp\n\nOriginal content.\n",
            "topics/finance.md": "# Finance\n\nOriginal topic content.\n",
            "summaries/1.md": "# Summary\n\nAuto-generated summary.\n",
        })

        sync_service.import_zip(zip_data)

        manifest_path = wiki_path / "sync_manifest.json"
        assert manifest_path.exists()

        manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert "last_sync" in manifest_data
        assert "file_hashes" in manifest_data
        assert len(manifest_data["file_hashes"]) > 0

    def test_manifest_tracks_file_hashes(
        self, sync_service: ObsidianSyncService, wiki_path: Path
    ):
        """Manifest should contain SHA256 hashes for all tracked files."""
        zip_data = _create_zip({
            "entities/acme-corp.md": "# Acme Corp\n\nOriginal content.\n",
            "topics/finance.md": "# Finance\n\nOriginal topic content.\n",
            "summaries/1.md": "# Summary\n\nAuto-generated summary.\n",
        })

        sync_service.import_zip(zip_data)

        manifest_path = wiki_path / "sync_manifest.json"
        manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))

        assert "entities/acme-corp.md" in manifest_data["file_hashes"]
        assert "topics/finance.md" in manifest_data["file_hashes"]
        assert "summaries/1.md" in manifest_data["file_hashes"]

        # Hashes should be 64 hex characters (SHA256)
        for _path, h in manifest_data["file_hashes"].items():
            assert len(h) == 64

    def test_manifest_updated_on_second_sync(
        self, sync_service: ObsidianSyncService, wiki_path: Path
    ):
        """Manifest should be updated on subsequent syncs."""
        zip_data1 = _create_zip({
            "entities/acme-corp.md": "# Acme Corp\n\nOriginal content.\n",
            "topics/finance.md": "# Finance\n\nOriginal topic content.\n",
            "summaries/1.md": "# Summary\n\nAuto-generated summary.\n",
        })
        sync_service.import_zip(zip_data1)

        manifest_path = wiki_path / "sync_manifest.json"
        first_data = json.loads(manifest_path.read_text(encoding="utf-8"))
        first_sync = first_data["last_sync"]

        # Second sync with changes
        zip_data2 = _create_zip({
            "entities/acme-corp.md": "# Acme Corp\n\nUpdated.\n",
            "topics/finance.md": "# Finance\n\nOriginal topic content.\n",
            "summaries/1.md": "# Summary\n\nAuto-generated summary.\n",
        })
        sync_service.import_zip(zip_data2)

        second_data = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert second_data["last_sync"] >= first_sync


class TestSyncAPIEndpoint:
    """Tests for the sync import API endpoint."""

    @pytest_asyncio.fixture
    async def sync_client(self, tmp_path: Path, wiki_path: Path) -> AsyncClient:
        """Create a test client with wiki and auth configured."""
        import app.api.obsidian_sync as obsidian_sync_module
        from app.core.security import get_current_user
        from app.main import app
        from app.models.user import User
        from app.services.obsidian_sync import ObsidianSyncService

        obsidian_sync_module.sync_service = ObsidianSyncService(
            wiki_path=str(wiki_path)
        )

        mock_user = User(
            id="test-sync-user",
            username="sync_tester",
            display_name="Sync Tester",
            email="sync@test.com",
            hashed_password="fakehash",
            is_active=True,
        )

        async def override_get_current_user() -> User:
            return mock_user

        app.dependency_overrides[get_current_user] = override_get_current_user

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac

        app.dependency_overrides.clear()

    @pytest.mark.anyio
    async def test_sync_import_endpoint(self, sync_client: AsyncClient, wiki_path: Path):
        """POST /api/wiki/sync/import should accept zip and return sync result."""
        zip_data = _create_zip({
            "entities/acme-corp.md": "# Acme Corp\n\nOriginal content.\n",
            "entities/brand-new.md": "# Brand New\n\nNew page.\n",
            "topics/finance.md": "# Finance\n\nOriginal topic content.\n",
            "summaries/1.md": "# Summary\n\nAuto-generated summary.\n",
        })

        response = await sync_client.post(
            "/api/wiki/sync/import",
            files={"file": ("vault.zip", zip_data, "application/zip")},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["pages_created"] == 1
        assert "conflicts" in data

    @pytest.mark.anyio
    async def test_sync_import_requires_auth(self, tmp_path: Path, wiki_path: Path):
        """POST /api/wiki/sync/import should require authentication."""
        from app.main import app

        app.dependency_overrides.clear()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            zip_data = _create_zip({"entities/test.md": "# Test\n"})
            response = await ac.post(
                "/api/wiki/sync/import",
                files={"file": ("vault.zip", zip_data, "application/zip")},
            )

        assert response.status_code == 401
