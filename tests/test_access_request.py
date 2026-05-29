"""Tests for the access request workflow."""

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select

from app.core.security import create_access_token, hash_password
from app.models.access_request import AccessRequest
from app.models.notification import Notification
from app.models.user import Role, User, UserRole
from app.services.access_request import AccessRequestService


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
    return db_session


@pytest_asyncio.fixture
async def admin_user(seeded_db):
    """Create an admin user."""
    from sqlalchemy import select as sa_select

    result = await seeded_db.execute(sa_select(Role).where(Role.code == "admin"))
    admin_role = result.scalar_one()

    user = User(
        username="arq_admin",
        email="arq_admin@edms.local",
        display_name="Access Request Admin",
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
    """Create a regular (non-admin) user."""
    from sqlalchemy import select as sa_select

    result = await seeded_db.execute(sa_select(Role).where(Role.code == "editor"))
    editor_role = result.scalar_one()

    user = User(
        username="arq_user",
        email="arq_user@edms.local",
        display_name="Regular User",
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


class TestCreateAccessRequest:
    """Tests for creating access requests."""

    async def test_create_access_request(self, client: AsyncClient, user_token):
        """Test creating an access request."""
        response = await client.post(
            "/api/request-access",
            json={
                "resource_type": "document",
                "resource_id": 1,
                "reason": "I need to review this document",
            },
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["resource_type"] == "document"
        assert data["resource_id"] == 1
        assert data["reason"] == "I need to review this document"
        assert data["status"] == "pending"

    async def test_create_access_request_no_reason(self, client: AsyncClient, user_token):
        """Test creating an access request without a reason."""
        response = await client.post(
            "/api/request-access",
            json={
                "resource_type": "group",
                "resource_id": 5,
            },
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["resource_type"] == "group"
        assert data["resource_id"] == 5
        assert data["reason"] is None
        assert data["status"] == "pending"

    async def test_create_access_request_invalid_resource_type(
        self, client: AsyncClient, user_token
    ):
        """Test creating an access request with invalid resource type."""
        response = await client.post(
            "/api/request-access",
            json={
                "resource_type": "invalid",
                "resource_id": 1,
            },
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert response.status_code == 400
        assert "resource_type" in response.json()["detail"]

    async def test_create_access_request_unauthenticated(self, client: AsyncClient):
        """Test creating an access request without authentication."""
        response = await client.post(
            "/api/request-access",
            json={
                "resource_type": "document",
                "resource_id": 1,
            },
        )
        assert response.status_code == 401


class TestListPendingRequests:
    """Tests for listing pending requests (admin only)."""

    async def test_list_pending_requests_admin(
        self, client: AsyncClient, admin_token, user_token
    ):
        """Test listing pending requests as admin."""
        # Create a request first
        await client.post(
            "/api/request-access",
            json={"resource_type": "document", "resource_id": 1},
            headers={"Authorization": f"Bearer {user_token}"},
        )

        response = await client.get(
            "/api/access-requests",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        assert data[0]["status"] == "pending"

    async def test_list_pending_requests_non_admin(
        self, client: AsyncClient, user_token
    ):
        """Test that non-admin cannot list pending requests."""
        response = await client.get(
            "/api/access-requests",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert response.status_code == 403


class TestListMyRequests:
    """Tests for listing current user's own requests."""

    async def test_list_my_requests(self, client: AsyncClient, user_token):
        """Test listing current user's access requests."""
        # Create some requests
        await client.post(
            "/api/request-access",
            json={"resource_type": "document", "resource_id": 10},
            headers={"Authorization": f"Bearer {user_token}"},
        )
        await client.post(
            "/api/request-access",
            json={"resource_type": "group", "resource_id": 3},
            headers={"Authorization": f"Bearer {user_token}"},
        )

        response = await client.get(
            "/api/access-requests/mine",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 2


class TestApproveAndDeny:
    """Tests for approve/deny workflow."""

    async def test_approve_request(
        self, client: AsyncClient, admin_token, user_token
    ):
        """Test approving an access request."""
        # Create a request
        create_resp = await client.post(
            "/api/request-access",
            json={"resource_type": "document", "resource_id": 1},
            headers={"Authorization": f"Bearer {user_token}"},
        )
        request_id = create_resp.json()["id"]

        # Approve it
        response = await client.post(
            f"/api/access-requests/{request_id}/approve",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "approved"
        assert data["reviewed_by"] is not None
        assert data["reviewed_at"] is not None

    async def test_deny_request(
        self, client: AsyncClient, admin_token, user_token
    ):
        """Test denying an access request."""
        # Create a request
        create_resp = await client.post(
            "/api/request-access",
            json={"resource_type": "document", "resource_id": 2, "reason": "test"},
            headers={"Authorization": f"Bearer {user_token}"},
        )
        request_id = create_resp.json()["id"]

        # Deny it
        response = await client.post(
            f"/api/access-requests/{request_id}/deny",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "denied"
        assert data["reviewed_by"] is not None
        assert data["reviewed_at"] is not None

    async def test_non_admin_cannot_approve(self, client: AsyncClient, user_token):
        """Test that non-admin cannot approve requests."""
        response = await client.post(
            "/api/access-requests/1/approve",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert response.status_code == 403

    async def test_non_admin_cannot_deny(self, client: AsyncClient, user_token):
        """Test that non-admin cannot deny requests."""
        response = await client.post(
            "/api/access-requests/1/deny",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert response.status_code == 403

    async def test_approve_nonexistent_request(
        self, client: AsyncClient, admin_token
    ):
        """Test approving a non-existent request returns 404."""
        response = await client.post(
            "/api/access-requests/99999/approve",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 404


class TestNotificationOnCreate:
    """Tests for notification being sent on access request creation."""

    async def test_notification_created(
        self, client: AsyncClient, user_token, db_session
    ):
        """Test that a notification is created when an access request is made."""
        response = await client.post(
            "/api/request-access",
            json={
                "resource_type": "document",
                "resource_id": 42,
                "reason": "Need access for review",
            },
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert response.status_code == 200

        # Check notification was created
        result = await db_session.execute(
            select(Notification).where(
                Notification.notification_type == "access_request"
            )
        )
        notifications = result.scalars().all()
        assert len(notifications) >= 1
        notif = notifications[-1]
        assert "access" in notif.title.lower()
        assert notif.data_json is not None
        assert notif.data_json["resource_id"] == 42


class TestAccessRequestService:
    """Tests for the AccessRequestService directly."""

    async def test_service_create_request(self, db_session, regular_user):
        """Test creating a request via the service."""
        service = AccessRequestService()
        req = await service.create_request(
            db_session,
            requester_id=regular_user.id,
            resource_type="document",
            resource_id=100,
            reason="Need for project",
        )
        assert req.id is not None
        assert req.status == "pending"
        assert req.requester_id == regular_user.id

    async def test_service_list_pending(self, db_session, regular_user):
        """Test listing pending requests via service."""
        service = AccessRequestService()
        await service.create_request(
            db_session, regular_user.id, "document", 1, "reason1"
        )
        await service.create_request(
            db_session, regular_user.id, "group", 2, "reason2"
        )

        pending = await service.list_pending(db_session)
        assert len(pending) >= 2

    async def test_service_approve(self, db_session, regular_user, admin_user):
        """Test approving a request via the service."""
        service = AccessRequestService()
        req = await service.create_request(
            db_session, regular_user.id, "document", 1, None
        )
        approved = await service.approve_request(db_session, req.id, admin_user.id)
        assert approved is not None
        assert approved.status == "approved"
        assert approved.reviewed_by == admin_user.id

    async def test_service_deny(self, db_session, regular_user, admin_user):
        """Test denying a request via the service."""
        service = AccessRequestService()
        req = await service.create_request(
            db_session, regular_user.id, "group", 5, "test"
        )
        denied = await service.deny_request(db_session, req.id, admin_user.id)
        assert denied is not None
        assert denied.status == "denied"
        assert denied.reviewed_by == admin_user.id
