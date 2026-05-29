from collections.abc import AsyncGenerator
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import get_db
from app.core.security import create_access_token
from app.main import app
from app.models.group import Base
from app.models.user import User


@pytest_asyncio.fixture
async def chat_db_session(tmp_path):
    """Create a DB session for chat tests."""
    db_path = tmp_path / "chat_test.db"
    db_url = f"sqlite+aiosqlite:///{db_path}"
    engine = create_async_engine(db_url, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest_asyncio.fixture
async def chat_user(chat_db_session: AsyncSession) -> User:
    """Create a test user."""
    from app.core.security import hash_password

    user = User(
        username="chatuser",
        display_name="Chat User",
        email="chatuser@test.com",
        hashed_password=hash_password("testpass"),
        is_active=True,
    )
    chat_db_session.add(user)
    await chat_db_session.flush()
    await chat_db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def chat_user2(chat_db_session: AsyncSession) -> User:
    """Create a second test user."""
    from app.core.security import hash_password

    user = User(
        username="chatuser2",
        display_name="Chat User 2",
        email="chatuser2@test.com",
        hashed_password=hash_password("testpass2"),
        is_active=True,
    )
    chat_db_session.add(user)
    await chat_db_session.flush()
    await chat_db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def chat_client(chat_db_session: AsyncSession, tmp_path):
    """Create a test client for chat endpoints."""
    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        try:
            yield chat_db_session
            await chat_db_session.commit()
        except Exception:
            await chat_db_session.rollback()
            raise

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


def _auth_headers(user: User) -> dict:
    """Generate auth headers for the given user."""
    token = create_access_token(data={"sub": user.username})
    return {"Authorization": f"Bearer {token}"}


class TestCreateSession:
    @pytest.mark.asyncio
    async def test_create_session_success(self, chat_client, chat_user):
        """Test creating a new chat session."""
        headers = _auth_headers(chat_user)
        response = await chat_client.post(
            "/api/chat/sessions",
            json={"title": "My Chat", "scope_type": "global"},
            headers=headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "My Chat"
        assert data["scope_type"] == "global"
        assert data["scope_id"] is None
        assert data["message_count"] == 0
        assert "id" in data
        assert "created_at" in data

    @pytest.mark.asyncio
    async def test_create_session_with_scope(self, chat_client, chat_user):
        """Test creating a session scoped to a group."""
        headers = _auth_headers(chat_user)
        response = await chat_client.post(
            "/api/chat/sessions",
            json={"title": "Group Chat", "scope_type": "group", "scope_id": 5},
            headers=headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["scope_type"] == "group"
        assert data["scope_id"] == 5

    @pytest.mark.asyncio
    async def test_create_session_unauthorized(self, chat_client):
        """Test that unauthenticated requests are rejected."""
        response = await chat_client.post(
            "/api/chat/sessions",
            json={"title": "No Auth"},
        )
        assert response.status_code == 401


class TestSendMessage:
    @pytest.mark.asyncio
    async def test_send_message_gets_response(self, chat_client, chat_user):
        """Test sending a message and getting an AI response with sources."""
        headers = _auth_headers(chat_user)

        # Create session first
        create_resp = await chat_client.post(
            "/api/chat/sessions",
            json={"title": "Test Chat"},
            headers=headers,
        )
        session_id = create_resp.json()["id"]

        mock_search_results = [
            {
                "chunk_text": "Python is a programming language.",
                "doc_id": 1,
                "score": 0.9,
            }
        ]

        with patch(
            "app.services.chat.generate_embeddings",
            return_value=[[0.1] * 1536],
        ), patch.object(
            type(app.state) if hasattr(app, "state") else object,
            "__getattr__",
            side_effect=AttributeError,
        ), patch(
            "app.services.chat.VectorDBService.search",
            return_value=mock_search_results,
        ), patch(
            "app.services.chat.chat_completion",
            return_value="Python is a high-level programming language.",
        ):
            response = await chat_client.post(
                f"/api/chat/sessions/{session_id}/messages",
                json={"message": "What is Python?"},
                headers=headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["message"]["role"] == "assistant"
        assert "Python" in data["message"]["content"]
        assert data["message"]["sources"] is not None
        assert len(data["message"]["sources"]) == 1
        assert data["message"]["sources"][0]["doc_id"] == 1
        assert data["session"]["id"] == session_id
        assert data["session"]["message_count"] == 2  # user + assistant

    @pytest.mark.asyncio
    async def test_send_message_session_not_found(self, chat_client, chat_user):
        """Test sending to a non-existent session returns 404."""
        headers = _auth_headers(chat_user)
        response = await chat_client.post(
            "/api/chat/sessions/nonexistent-id/messages",
            json={"message": "Hello"},
            headers=headers,
        )
        assert response.status_code == 404


class TestMultiTurnContext:
    @pytest.mark.asyncio
    async def test_multi_turn_sends_history(self, chat_client, chat_user):
        """Test that multi-turn conversations maintain history."""
        headers = _auth_headers(chat_user)

        # Create session
        create_resp = await chat_client.post(
            "/api/chat/sessions",
            json={"title": "Multi-turn"},
            headers=headers,
        )
        session_id = create_resp.json()["id"]

        captured_messages = []

        def mock_chat_completion(messages, context):
            captured_messages.append(messages)
            return f"Response to turn {len(messages)}"

        with patch(
            "app.services.chat.generate_embeddings",
            return_value=[[0.1] * 1536],
        ), patch(
            "app.services.chat.VectorDBService.search",
            return_value=[],
        ), patch(
            "app.services.chat.chat_completion",
            side_effect=mock_chat_completion,
        ):
            # First message
            await chat_client.post(
                f"/api/chat/sessions/{session_id}/messages",
                json={"message": "Hello"},
                headers=headers,
            )

            # Second message should include history
            await chat_client.post(
                f"/api/chat/sessions/{session_id}/messages",
                json={"message": "Tell me more"},
                headers=headers,
            )

        # First call should have 1 message (user)
        assert len(captured_messages[0]) == 1
        assert captured_messages[0][0]["content"] == "Hello"

        # Second call should have 3 messages (user, assistant, user)
        assert len(captured_messages[1]) == 3
        assert captured_messages[1][0]["role"] == "user"
        assert captured_messages[1][0]["content"] == "Hello"
        assert captured_messages[1][1]["role"] == "assistant"
        assert captured_messages[1][2]["role"] == "user"
        assert captured_messages[1][2]["content"] == "Tell me more"


class TestScopedChat:
    @pytest.mark.asyncio
    async def test_scoped_chat_filters_by_group(self, chat_client, chat_user):
        """Test that group-scoped chat uses group_id filter in search."""
        headers = _auth_headers(chat_user)

        # Create a group-scoped session
        create_resp = await chat_client.post(
            "/api/chat/sessions",
            json={"title": "Group Scoped", "scope_type": "group", "scope_id": 42},
            headers=headers,
        )
        session_id = create_resp.json()["id"]

        search_calls = []

        def mock_search(self, query_embedding, group_id=None, top_k=5):
            search_calls.append({"group_id": group_id, "top_k": top_k})
            return []

        with patch(
            "app.services.chat.generate_embeddings",
            return_value=[[0.1] * 1536],
        ), patch(
            "app.services.chat.VectorDBService.search",
            mock_search,
        ), patch(
            "app.services.chat.chat_completion",
            return_value="Scoped answer",
        ):
            await chat_client.post(
                f"/api/chat/sessions/{session_id}/messages",
                json={"message": "Query within group"},
                headers=headers,
            )

        # Verify search was called with the group_id filter
        assert len(search_calls) == 1
        assert search_calls[0]["group_id"] == 42


class TestExportSession:
    @pytest.mark.asyncio
    async def test_export_markdown(self, chat_client, chat_user):
        """Test exporting a session as markdown."""
        headers = _auth_headers(chat_user)

        # Create session and send a message
        create_resp = await chat_client.post(
            "/api/chat/sessions",
            json={"title": "Export Test"},
            headers=headers,
        )
        session_id = create_resp.json()["id"]

        with patch(
            "app.services.chat.generate_embeddings",
            return_value=[[0.1] * 1536],
        ), patch(
            "app.services.chat.VectorDBService.search",
            return_value=[],
        ), patch(
            "app.services.chat.chat_completion",
            return_value="This is the answer.",
        ):
            await chat_client.post(
                f"/api/chat/sessions/{session_id}/messages",
                json={"message": "What is this?"},
                headers=headers,
            )

        # Export
        response = await chat_client.get(
            f"/api/chat/sessions/{session_id}/export?format=markdown",
            headers=headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["format"] == "markdown"
        assert "## Session: Export Test" in data["content"]
        assert "**User:** What is this?" in data["content"]
        assert "**Assistant:** This is the answer." in data["content"]


class TestListSessions:
    @pytest.mark.asyncio
    async def test_list_sessions_returns_user_sessions(
        self, chat_client, chat_user, chat_user2
    ):
        """Test that list sessions only returns the current user's sessions."""
        headers1 = _auth_headers(chat_user)
        headers2 = _auth_headers(chat_user2)

        # User 1 creates sessions
        await chat_client.post(
            "/api/chat/sessions",
            json={"title": "User1 Session A"},
            headers=headers1,
        )
        await chat_client.post(
            "/api/chat/sessions",
            json={"title": "User1 Session B"},
            headers=headers1,
        )

        # User 2 creates a session
        await chat_client.post(
            "/api/chat/sessions",
            json={"title": "User2 Session"},
            headers=headers2,
        )

        # User 1 should only see their sessions
        response = await chat_client.get(
            "/api/chat/sessions",
            headers=headers1,
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        titles = [s["title"] for s in data]
        assert "User1 Session A" in titles
        assert "User1 Session B" in titles
        assert "User2 Session" not in titles


class TestDeleteSession:
    @pytest.mark.asyncio
    async def test_delete_session_removes_all_messages(self, chat_client, chat_user):
        """Test that deleting a session removes all its messages."""
        headers = _auth_headers(chat_user)

        # Create session and send a message
        create_resp = await chat_client.post(
            "/api/chat/sessions",
            json={"title": "To Delete"},
            headers=headers,
        )
        session_id = create_resp.json()["id"]

        with patch(
            "app.services.chat.generate_embeddings",
            return_value=[[0.1] * 1536],
        ), patch(
            "app.services.chat.VectorDBService.search",
            return_value=[],
        ), patch(
            "app.services.chat.chat_completion",
            return_value="Response",
        ):
            await chat_client.post(
                f"/api/chat/sessions/{session_id}/messages",
                json={"message": "Hello"},
                headers=headers,
            )

        # Delete
        response = await chat_client.delete(
            f"/api/chat/sessions/{session_id}",
            headers=headers,
        )
        assert response.status_code == 200
        assert response.json()["detail"] == "Session deleted"

        # Verify session is gone
        list_resp = await chat_client.get(
            "/api/chat/sessions",
            headers=headers,
        )
        assert len(list_resp.json()) == 0

    @pytest.mark.asyncio
    async def test_delete_session_not_found(self, chat_client, chat_user):
        """Test deleting a non-existent session returns 404."""
        headers = _auth_headers(chat_user)
        response = await chat_client.delete(
            "/api/chat/sessions/nonexistent-id",
            headers=headers,
        )
        assert response.status_code == 404


class TestUnauthorizedAccess:
    @pytest.mark.asyncio
    async def test_cannot_access_other_users_session(
        self, chat_client, chat_user, chat_user2
    ):
        """Test that a user cannot access another user's session."""
        headers1 = _auth_headers(chat_user)
        headers2 = _auth_headers(chat_user2)

        # User 1 creates a session
        create_resp = await chat_client.post(
            "/api/chat/sessions",
            json={"title": "Private"},
            headers=headers1,
        )
        session_id = create_resp.json()["id"]

        # User 2 tries to access it
        response = await chat_client.get(
            f"/api/chat/sessions/{session_id}/messages",
            headers=headers2,
        )
        assert response.status_code == 404

        # User 2 tries to delete it
        response = await chat_client.delete(
            f"/api/chat/sessions/{session_id}",
            headers=headers2,
        )
        assert response.status_code == 404
