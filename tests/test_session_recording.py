"""Tests for the session recording feature."""

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import AsyncClient

from app.core.security import create_access_token, hash_password
from app.models.document import Document, DocumentStatus
from app.models.group import Group
from app.models.session import SessionDocument, UserSession
from app.models.user import Role, User, UserRole
from app.services.session_recording import SessionRecordingService, record_access


@pytest_asyncio.fixture
async def seeded_db(db_session):
    """Seed roles into the test database."""
    roles_data = [
        ("admin", "Administrator"),
        ("editor", "Editor"),
    ]
    for code, name in roles_data:
        db_session.add(
            Role(code=code, name=name, description=f"{code} role", is_system=True)
        )
    await db_session.flush()

    # Create a group and document for session recording tests
    group = Group(name="Test Group", description="Test group")
    db_session.add(group)
    await db_session.flush()
    await db_session.refresh(group)

    doc = Document(
        group_id=group.id,
        original_filename="test.pdf",
        storage_path="/storage/test.pdf",
        file_type="application/pdf",
        file_size=1024,
        status=DocumentStatus.processed,
    )
    db_session.add(doc)
    await db_session.flush()

    return db_session


@pytest_asyncio.fixture
async def admin_user(seeded_db):
    """Create an admin user."""
    from sqlalchemy import select

    result = await seeded_db.execute(select(Role).where(Role.code == "admin"))
    admin_role = result.scalar_one()

    user = User(
        username="session_admin",
        email="session_admin@edms.local",
        display_name="Session Admin",
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
    """Create a regular user."""
    from sqlalchemy import select

    result = await seeded_db.execute(select(Role).where(Role.code == "editor"))
    editor_role = result.scalar_one()

    user = User(
        username="session_user",
        email="session_user@edms.local",
        display_name="Session User",
        hashed_password=hash_password("password"),
    )
    seeded_db.add(user)
    await seeded_db.flush()
    await seeded_db.refresh(user)

    user_role = UserRole(user_id=user.id, role_id=editor_role.id)
    seeded_db.add(user_role)
    await seeded_db.flush()
    await seeded_db.refresh(user)
    return user


@pytest_asyncio.fixture
async def admin_token(admin_user):
    """Create a valid JWT token for the admin user."""
    return create_access_token(data={"sub": admin_user.username})


@pytest_asyncio.fixture
async def user_token(regular_user):
    """Create a valid JWT token for the regular user."""
    return create_access_token(data={"sub": regular_user.username})


class TestSessionRecordingService:
    """Tests for SessionRecordingService."""

    async def test_get_or_create_session_creates_new(self, seeded_db, regular_user):
        """Test that get_or_create_session creates a new session."""
        service = SessionRecordingService()
        session = await service.get_or_create_session(
            seeded_db, regular_user.id, "192.168.1.1", "TestAgent/1.0"
        )
        assert session is not None
        assert session.user_id == regular_user.id
        assert session.ip_address == "192.168.1.1"
        assert session.user_agent == "TestAgent/1.0"
        assert session.ended_at is None

    async def test_get_or_create_session_returns_existing(self, seeded_db, regular_user):
        """Test that get_or_create_session returns existing active session."""
        service = SessionRecordingService()

        # Create first session
        session1 = await service.get_or_create_session(
            seeded_db, regular_user.id, "10.0.0.1", "Agent/1.0"
        )

        # Should return same session
        session2 = await service.get_or_create_session(
            seeded_db, regular_user.id, "10.0.0.1", "Agent/1.0"
        )

        assert session1.id == session2.id

    async def test_get_or_create_session_new_for_different_ip(
        self, seeded_db, regular_user
    ):
        """Test that different IPs create different sessions."""
        service = SessionRecordingService()

        session1 = await service.get_or_create_session(
            seeded_db, regular_user.id, "10.0.0.1", "Agent/1.0"
        )
        session2 = await service.get_or_create_session(
            seeded_db, regular_user.id, "10.0.0.2", "Agent/1.0"
        )

        assert session1.id != session2.id

    async def test_record_document_access(self, seeded_db, regular_user):
        """Test recording document access."""
        service = SessionRecordingService()
        doc_access = await service.record_document_access(
            seeded_db, regular_user.id, 1, "view", "192.168.1.1", "Agent/1.0"
        )
        assert doc_access is not None
        assert doc_access.document_id == 1
        assert doc_access.action == "view"
        assert doc_access.session_id is not None

    async def test_end_session(self, seeded_db, regular_user):
        """Test ending a session."""
        service = SessionRecordingService()
        session = await service.get_or_create_session(
            seeded_db, regular_user.id, "192.168.1.1", "Agent"
        )
        assert session.ended_at is None

        await service.end_session(seeded_db, session.id)
        await seeded_db.refresh(session)
        assert session.ended_at is not None

    async def test_list_sessions(self, seeded_db, regular_user):
        """Test listing sessions."""
        service = SessionRecordingService()

        # Create some sessions
        await service.get_or_create_session(
            seeded_db, regular_user.id, "10.0.0.1", "Agent/1.0"
        )
        await service.get_or_create_session(
            seeded_db, regular_user.id, "10.0.0.2", "Agent/2.0"
        )

        sessions, total = await service.list_sessions(seeded_db)
        assert total >= 2
        assert len(sessions) >= 2

    async def test_list_sessions_with_date_filter(self, seeded_db, regular_user):
        """Test listing sessions with date filtering."""
        service = SessionRecordingService()

        await service.get_or_create_session(
            seeded_db, regular_user.id, "10.0.0.1", "Agent"
        )

        # Filter for future dates should return no sessions
        future = datetime.now(timezone.utc) + timedelta(days=1)
        sessions, total = await service.list_sessions(seeded_db, start_date=future)
        assert total == 0

    async def test_list_sessions_with_user_filter(self, seeded_db, regular_user):
        """Test listing sessions filtered by user."""
        service = SessionRecordingService()

        await service.get_or_create_session(
            seeded_db, regular_user.id, "10.0.0.1", "Agent"
        )

        sessions, total = await service.list_sessions(
            seeded_db, user_id_filter=regular_user.id
        )
        assert total >= 1
        for s in sessions:
            assert s.user_id == regular_user.id

    async def test_get_session_detail(self, seeded_db, regular_user):
        """Test getting session detail with document access."""
        service = SessionRecordingService()

        # Record some document accesses
        await service.record_document_access(
            seeded_db, regular_user.id, 1, "view", "192.168.1.1", "Agent"
        )
        await service.record_document_access(
            seeded_db, regular_user.id, 1, "download", "192.168.1.1", "Agent"
        )

        # Get the session
        sessions, _ = await service.list_sessions(
            seeded_db, user_id_filter=regular_user.id
        )
        assert len(sessions) >= 1

        detail = await service.get_session_detail(seeded_db, sessions[0].id)
        assert detail is not None
        assert len(detail.documents) >= 2


class TestRecordAccessHelper:
    """Tests for the record_access helper function."""

    async def test_record_access_helper(self, seeded_db, regular_user):
        """Test the fire-and-forget record_access helper."""
        await record_access(
            seeded_db, regular_user.id, 1, "view", "192.168.1.1", "Agent"
        )

        service = SessionRecordingService()
        sessions, total = await service.list_sessions(
            seeded_db, user_id_filter=regular_user.id
        )
        assert total >= 1

    async def test_record_access_does_not_raise(self, seeded_db):
        """Test that record_access swallows errors."""
        # Pass invalid user_id - FK constraint might not raise in SQLite
        # but the function should handle errors gracefully
        await record_access(
            seeded_db, "nonexistent_user_id", 99999, "view", "1.2.3.4", "Agent"
        )


class TestSessionsAPI:
    """Tests for session recording API endpoints."""

    async def test_list_sessions_admin(self, client: AsyncClient, admin_token):
        """Test listing sessions as admin."""
        response = await client.get(
            "/api/sessions",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "sessions" in data
        assert "total" in data

    async def test_list_sessions_non_admin(self, client: AsyncClient, user_token):
        """Test that non-admin cannot list sessions."""
        response = await client.get(
            "/api/sessions",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert response.status_code == 403

    async def test_list_sessions_unauthenticated(self, client: AsyncClient):
        """Test that unauthenticated user cannot list sessions."""
        response = await client.get("/api/sessions")
        assert response.status_code == 401

    async def test_list_sessions_with_date_filter(
        self, client: AsyncClient, admin_token
    ):
        """Test listing sessions with date parameters."""
        response = await client.get(
            "/api/sessions",
            params={
                "start_date": "2020-01-01T00:00:00",
                "end_date": "2030-12-31T23:59:59",
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200

    async def test_list_sessions_invalid_date(self, client: AsyncClient, admin_token):
        """Test listing sessions with invalid date."""
        response = await client.get(
            "/api/sessions",
            params={"start_date": "not-a-date"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 400

    async def test_get_session_detail_admin(
        self, client: AsyncClient, admin_token, seeded_db, regular_user
    ):
        """Test getting session detail as admin."""
        # Create a session via service
        service = SessionRecordingService()
        session = await service.get_or_create_session(
            seeded_db, regular_user.id, "192.168.1.100", "TestBrowser/1.0"
        )
        await seeded_db.commit()

        response = await client.get(
            f"/api/sessions/{session.id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == session.id
        assert data["user_id"] == regular_user.id

    async def test_get_session_detail_non_admin(
        self, client: AsyncClient, user_token
    ):
        """Test that non-admin cannot get session detail."""
        response = await client.get(
            "/api/sessions/some-session-id",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert response.status_code == 403

    async def test_get_session_detail_not_found(
        self, client: AsyncClient, admin_token
    ):
        """Test getting non-existent session detail."""
        response = await client.get(
            "/api/sessions/nonexistent-id",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 404
