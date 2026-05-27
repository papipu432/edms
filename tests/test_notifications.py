"""Tests for the real-time notifications feature."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models.notification import Notification
from app.models.user import User, Role, UserRole
from app.services.notifications import NotificationManager, get_notification_manager


@pytest_asyncio.fixture
async def auth_user(db_session: AsyncSession) -> tuple[User, str]:
    """Create a test user and return user + JWT token."""
    from app.core.security import hash_password

    user = User(
        username="notifyuser",
        display_name="Notify User",
        email="notify@test.com",
        hashed_password=hash_password("password123"),
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()

    token = create_access_token(data={"sub": user.username})
    return user, token


@pytest_asyncio.fixture
async def admin_user(db_session: AsyncSession) -> tuple[User, str]:
    """Create an admin user and return user + JWT token."""
    from app.core.security import hash_password

    # Create admin role
    role = Role(code="admin", name="Administrator", is_system=True)
    db_session.add(role)
    await db_session.flush()

    user = User(
        username="notifyadmin",
        display_name="Admin User",
        email="admin_notify@test.com",
        hashed_password=hash_password("password123"),
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()

    user_role = UserRole(user_id=user.id, role_id=role.id)
    db_session.add(user_role)
    await db_session.flush()

    token = create_access_token(data={"sub": user.username})
    return user, token


class TestNotificationModel:
    """Tests for the Notification model."""

    @pytest.mark.asyncio
    async def test_create_notification(self, db_session: AsyncSession, auth_user):
        """Test creating a notification record in the database."""
        user, _ = auth_user
        notification = Notification(
            user_id=user.id,
            notification_type="document_status",
            title="Test Notification",
            message="This is a test notification.",
            data_json={"key": "value"},
            is_read=False,
        )
        db_session.add(notification)
        await db_session.flush()

        result = await db_session.execute(
            select(Notification).where(Notification.id == notification.id)
        )
        saved = result.scalar_one()
        assert saved.user_id == user.id
        assert saved.notification_type == "document_status"
        assert saved.title == "Test Notification"
        assert saved.message == "This is a test notification."
        assert saved.data_json == {"key": "value"}
        assert saved.is_read is False
        assert saved.created_at is not None

    @pytest.mark.asyncio
    async def test_create_broadcast_notification(self, db_session: AsyncSession):
        """Test creating a broadcast notification (user_id is None)."""
        notification = Notification(
            user_id=None,
            notification_type="system",
            title="System Broadcast",
            message="System maintenance scheduled.",
        )
        db_session.add(notification)
        await db_session.flush()

        result = await db_session.execute(
            select(Notification).where(Notification.id == notification.id)
        )
        saved = result.scalar_one()
        assert saved.user_id is None
        assert saved.notification_type == "system"


class TestNotificationRESTEndpoints:
    """Tests for the notifications REST API endpoints."""

    @pytest.mark.asyncio
    async def test_list_notifications(self, client: AsyncClient, db_session: AsyncSession, auth_user):
        """Test listing notifications for the authenticated user."""
        user, token = auth_user

        # Create some notifications for this user
        for i in range(3):
            n = Notification(
                user_id=user.id,
                notification_type="document_status",
                title=f"Notification {i}",
                message=f"Message {i}",
            )
            db_session.add(n)
        await db_session.flush()

        response = await client.get(
            "/api/notifications",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 3

    @pytest.mark.asyncio
    async def test_list_notifications_includes_broadcasts(
        self, client: AsyncClient, db_session: AsyncSession, auth_user
    ):
        """Test that listing notifications includes broadcast notifications."""
        user, token = auth_user

        # Create a user-specific notification
        n1 = Notification(
            user_id=user.id,
            notification_type="document_status",
            title="User Notification",
            message="For user",
        )
        # Create a broadcast notification
        n2 = Notification(
            user_id=None,
            notification_type="system",
            title="Broadcast",
            message="For everyone",
        )
        db_session.add(n1)
        db_session.add(n2)
        await db_session.flush()

        response = await client.get(
            "/api/notifications",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

    @pytest.mark.asyncio
    async def test_list_notifications_unauthenticated(self, client: AsyncClient):
        """Test that listing notifications requires authentication."""
        response = await client.get("/api/notifications")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_mark_notification_read(
        self, client: AsyncClient, db_session: AsyncSession, auth_user
    ):
        """Test marking a notification as read."""
        user, token = auth_user

        notification = Notification(
            user_id=user.id,
            notification_type="document_status",
            title="Test",
            message="Test message",
            is_read=False,
        )
        db_session.add(notification)
        await db_session.flush()

        response = await client.post(
            f"/api/notifications/{notification.id}/read",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["is_read"] is True

        # Verify in DB
        await db_session.refresh(notification)
        assert notification.is_read is True

    @pytest.mark.asyncio
    async def test_mark_all_notifications_read(
        self, client: AsyncClient, db_session: AsyncSession, auth_user
    ):
        """Test marking all notifications as read."""
        user, token = auth_user

        for i in range(3):
            n = Notification(
                user_id=user.id,
                notification_type="document_status",
                title=f"Notification {i}",
                message=f"Message {i}",
                is_read=False,
            )
            db_session.add(n)
        await db_session.flush()

        response = await client.post(
            "/api/notifications/read-all",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200

        # Verify all are read
        result = await db_session.execute(
            select(Notification).where(
                Notification.user_id == user.id,
                Notification.is_read == False,  # noqa: E712
            )
        )
        unread = result.scalars().all()
        assert len(unread) == 0

    @pytest.mark.asyncio
    async def test_unread_count(
        self, client: AsyncClient, db_session: AsyncSession, auth_user
    ):
        """Test getting unread notification count."""
        user, token = auth_user

        # Create 2 unread and 1 read notification
        for i in range(2):
            n = Notification(
                user_id=user.id,
                notification_type="document_status",
                title=f"Unread {i}",
                message=f"Message {i}",
                is_read=False,
            )
            db_session.add(n)
        read_n = Notification(
            user_id=user.id,
            notification_type="document_status",
            title="Read",
            message="Read message",
            is_read=True,
        )
        db_session.add(read_n)
        await db_session.flush()

        response = await client.get(
            "/api/notifications/unread-count",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["unread_count"] == 2

    @pytest.mark.asyncio
    async def test_pagination(
        self, client: AsyncClient, db_session: AsyncSession, auth_user
    ):
        """Test notification pagination with limit and offset."""
        user, token = auth_user

        for i in range(10):
            n = Notification(
                user_id=user.id,
                notification_type="document_status",
                title=f"Notification {i}",
                message=f"Message {i}",
            )
            db_session.add(n)
        await db_session.flush()

        response = await client.get(
            "/api/notifications?limit=3&offset=0",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 3

        response = await client.get(
            "/api/notifications?limit=5&offset=5",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 5


class TestNotificationManager:
    """Tests for the NotificationManager singleton."""

    @pytest.mark.asyncio
    async def test_singleton(self):
        """Test that get_notification_manager returns same instance."""
        manager1 = get_notification_manager()
        manager2 = get_notification_manager()
        assert manager1 is manager2

    @pytest.mark.asyncio
    async def test_connect_disconnect(self):
        """Test registering and removing WebSocket connections."""
        manager = NotificationManager()
        ws = MagicMock()

        manager.connect("user-1", ws)
        assert "user-1" in manager._connections
        assert len(manager._connections["user-1"]) == 1

        manager.disconnect("user-1", ws)
        assert "user-1" not in manager._connections

    @pytest.mark.asyncio
    async def test_send_to_user(self):
        """Test sending a notification to a specific user."""
        manager = NotificationManager()
        ws = AsyncMock()

        manager.connect("user-1", ws)
        await manager.send_to_user("user-1", {"title": "Hello"})

        ws.send_text.assert_called_once_with(json.dumps({"title": "Hello"}))

    @pytest.mark.asyncio
    async def test_broadcast(self):
        """Test broadcasting a notification to all connected users."""
        manager = NotificationManager()
        ws1 = AsyncMock()
        ws2 = AsyncMock()

        manager.connect("user-1", ws1)
        manager.connect("user-2", ws2)

        await manager.broadcast({"title": "Broadcast"})

        expected = json.dumps({"title": "Broadcast"})
        ws1.send_text.assert_called_once_with(expected)
        ws2.send_text.assert_called_once_with(expected)

    @pytest.mark.asyncio
    async def test_create_notification_persists(self, db_session: AsyncSession, auth_user):
        """Test that create_notification persists to database."""
        user, _ = auth_user
        manager = NotificationManager()

        notification = await manager.create_notification(
            db=db_session,
            user_id=user.id,
            notification_type="document_status",
            title="Persisted",
            message="This is persisted",
            data={"doc_id": "123"},
        )

        result = await db_session.execute(
            select(Notification).where(Notification.id == notification.id)
        )
        saved = result.scalar_one()
        assert saved.title == "Persisted"
        assert saved.data_json == {"doc_id": "123"}

    @pytest.mark.asyncio
    async def test_notify_document_status(self, db_session: AsyncSession, auth_user):
        """Test the notify_document_status helper."""
        user, _ = auth_user
        manager = NotificationManager()

        notification = await manager.notify_document_status(
            db=db_session,
            doc_id="doc-1",
            doc_name="Report.pdf",
            status="approved",
            user_id=user.id,
        )

        assert notification.notification_type == "document_status"
        assert "Report.pdf" in notification.message
        assert notification.data_json["status"] == "approved"

    @pytest.mark.asyncio
    async def test_notify_ransomware_alert(self, db_session: AsyncSession):
        """Test the notify_ransomware_alert helper."""
        manager = NotificationManager()

        notification = await manager.notify_ransomware_alert(
            db=db_session,
            alert_data={"message": "Suspicious file detected", "path": "/tmp/bad.exe"},
        )

        assert notification.notification_type == "ransomware_alert"
        assert notification.user_id is None  # broadcast
        assert "Suspicious file detected" in notification.message

    @pytest.mark.asyncio
    async def test_notify_backup_status(self, db_session: AsyncSession, auth_user):
        """Test the notify_backup_status helper."""
        user, _ = auth_user
        manager = NotificationManager()

        notification = await manager.notify_backup_status(
            db=db_session,
            job_id="job-123",
            status="completed",
            target="minio-primary",
            user_id=user.id,
        )

        assert notification.notification_type == "backup_status"
        assert notification.data_json["job_id"] == "job-123"

    @pytest.mark.asyncio
    async def test_disconnect_on_send_failure(self):
        """Test that failed sends result in disconnection."""
        manager = NotificationManager()
        ws = AsyncMock()
        ws.send_text.side_effect = Exception("Connection closed")

        manager.connect("user-1", ws)
        await manager.send_to_user("user-1", {"title": "Fail"})

        # The connection should be removed after failure
        assert "user-1" not in manager._connections


class TestWebSocketAuth:
    """Tests for WebSocket authentication."""

    @pytest.mark.asyncio
    async def test_websocket_invalid_token_rejected(self, client: AsyncClient):
        """Test that WebSocket connection with invalid token is rejected."""
        # We test via the REST approach since httpx doesn't natively support WS
        # Instead, we test the token verification function directly
        from app.api.websocket import _verify_ws_token

        result = _verify_ws_token("invalid-token-here")
        assert result is None

    @pytest.mark.asyncio
    async def test_websocket_valid_token_returns_username(self, auth_user):
        """Test that a valid token returns the correct username."""
        from app.api.websocket import _verify_ws_token

        user, token = auth_user
        result = _verify_ws_token(token)
        assert result == user.username

    @pytest.mark.asyncio
    async def test_websocket_expired_token_rejected(self):
        """Test that an expired token is rejected."""
        from datetime import timedelta

        from app.api.websocket import _verify_ws_token

        token = create_access_token(
            data={"sub": "testuser"}, expires_delta=timedelta(seconds=-10)
        )
        result = _verify_ws_token(token)
        assert result is None
