"""Tests for the Daily Notes feature."""

from pathlib import Path
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.daily_notes import DailyNotesService


@pytest_asyncio.fixture
async def daily_notes_client(tmp_path: Path, db_session: AsyncSession) -> AsyncClient:
    """Create a test client with wiki path, auth, and DB configured."""
    import app.api.daily_notes as daily_notes_module
    from app.core.database import get_db
    from app.core.security import get_current_user
    from app.main import app
    from app.models.user import User
    from app.services.daily_notes import DailyNotesService

    wiki = tmp_path / "wiki"
    wiki.mkdir()

    daily_notes_module.daily_notes_service = DailyNotesService(wiki_path=str(wiki))

    mock_user = User(
        id="test-daily-user",
        username="daily_tester",
        display_name="Daily Tester",
        email="daily@test.com",
        hashed_password="fakehash",
        is_active=True,
    )

    async def override_get_current_user() -> User:
        return mock_user

    async def override_get_db():
        try:
            yield db_session
            await db_session.commit()
        except Exception:
            await db_session.rollback()
            raise

    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


class TestDailyNoteGeneration:
    """Tests for daily note generation endpoint."""

    @pytest.mark.anyio
    async def test_generate_daily_note(self, daily_notes_client: AsyncClient, tmp_path: Path):
        """POST /api/wiki/daily-note should generate a daily note."""
        response = await daily_notes_client.post("/api/wiki/daily-note")

        assert response.status_code == 200
        data = response.json()
        assert "date" in data
        assert "path" in data
        assert "content" in data
        assert data["path"].startswith("daily/")
        assert "Daily Note" in data["content"]

    @pytest.mark.anyio
    async def test_generate_daily_note_creates_file(
        self, daily_notes_client: AsyncClient, tmp_path: Path
    ):
        """Daily note generation should create a file on disk."""
        response = await daily_notes_client.post("/api/wiki/daily-note")

        assert response.status_code == 200
        data = response.json()
        wiki = tmp_path / "wiki"
        note_path = wiki / data["path"]
        assert note_path.exists()


class TestDailyNotesList:
    """Tests for daily notes list endpoint."""

    @pytest.mark.anyio
    async def test_list_daily_notes_empty(self, daily_notes_client: AsyncClient):
        """GET /api/wiki/daily-notes should return empty list when none exist."""
        response = await daily_notes_client.get("/api/wiki/daily-notes")

        assert response.status_code == 200
        data = response.json()
        assert "notes" in data
        assert data["notes"] == []

    @pytest.mark.anyio
    async def test_list_daily_notes_after_generation(self, daily_notes_client: AsyncClient):
        """GET /api/wiki/daily-notes should include generated note."""
        # Generate a note first
        await daily_notes_client.post("/api/wiki/daily-note")

        response = await daily_notes_client.get("/api/wiki/daily-notes")

        assert response.status_code == 200
        data = response.json()
        assert len(data["notes"]) == 1
        assert "date" in data["notes"][0]
        assert "path" in data["notes"][0]
