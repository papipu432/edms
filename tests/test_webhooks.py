"""Tests for webhook integrations."""

import hashlib
import hmac
import json

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password
from app.models.user import Role, User, UserRole
from app.models.webhook import WebhookConfig
from app.services.webhooks import WebhookService


async def _create_admin_user(db: AsyncSession, username: str = "admin") -> tuple[User, str]:
    """Create an admin user and return (user, token)."""
    existing = await db.execute(select(Role).where(Role.code == "admin"))
    if existing.scalar_one_or_none() is None:
        db.add(Role(code="admin", name="Admin", description="Admin role", is_system=True))
    await db.flush()

    user = User(
        username=username,
        email=f"{username}@example.com",
        display_name="Admin User",
        hashed_password=hash_password("password123"),
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)

    result = await db.execute(select(Role).where(Role.code == "admin"))
    role = result.scalar_one()
    user_role = UserRole(user_id=user.id, role_id=role.id)
    db.add(user_role)
    await db.flush()
    await db.refresh(user)

    token = create_access_token(data={"sub": user.username})
    return user, token


@pytest.mark.asyncio
async def test_create_webhook(client: AsyncClient, db_session: AsyncSession):
    """Test creating a webhook configuration."""
    _, token = await _create_admin_user(db_session)

    response = await client.post(
        "/api/webhooks",
        json={
            "url": "https://example.com/webhook",
            "secret": "mysecret123",
            "events": ["document.uploaded", "document.approved"],
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["url"] == "https://example.com/webhook"
    assert data["events"] == ["document.uploaded", "document.approved"]
    assert data["is_active"] is True


@pytest.mark.asyncio
async def test_list_webhooks(client: AsyncClient, db_session: AsyncSession):
    """Test listing webhooks."""
    _, token = await _create_admin_user(db_session)

    webhook = WebhookConfig(
        url="https://example.com/hook",
        secret="secret",
        events=["document.uploaded"],
    )
    db_session.add(webhook)
    await db_session.flush()

    response = await client.get(
        "/api/webhooks",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1


@pytest.mark.asyncio
async def test_get_webhook(client: AsyncClient, db_session: AsyncSession):
    """Test getting a specific webhook."""
    _, token = await _create_admin_user(db_session)

    webhook = WebhookConfig(
        url="https://example.com/get",
        secret="getsecret",
        events=["lifecycle.alert"],
    )
    db_session.add(webhook)
    await db_session.flush()
    await db_session.refresh(webhook)

    response = await client.get(
        f"/api/webhooks/{webhook.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["url"] == "https://example.com/get"


@pytest.mark.asyncio
async def test_update_webhook(client: AsyncClient, db_session: AsyncSession):
    """Test updating a webhook."""
    _, token = await _create_admin_user(db_session)

    webhook = WebhookConfig(
        url="https://example.com/old",
        secret="oldsecret",
        events=["document.uploaded"],
    )
    db_session.add(webhook)
    await db_session.flush()
    await db_session.refresh(webhook)

    response = await client.put(
        f"/api/webhooks/{webhook.id}",
        json={"url": "https://example.com/new"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["url"] == "https://example.com/new"


@pytest.mark.asyncio
async def test_delete_webhook(client: AsyncClient, db_session: AsyncSession):
    """Test deleting a webhook."""
    _, token = await _create_admin_user(db_session)

    webhook = WebhookConfig(
        url="https://example.com/delete",
        secret="delsecret",
        events=["backup.completed"],
    )
    db_session.add(webhook)
    await db_session.flush()
    await db_session.refresh(webhook)

    response = await client.delete(
        f"/api/webhooks/{webhook.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 204


@pytest.mark.asyncio
async def test_webhook_test_endpoint(client: AsyncClient, db_session: AsyncSession):
    """Test the webhook test endpoint."""
    _, token = await _create_admin_user(db_session)

    webhook = WebhookConfig(
        url="https://httpbin.org/post",
        secret="testsecret",
        events=["document.uploaded"],
    )
    db_session.add(webhook)
    await db_session.flush()
    await db_session.refresh(webhook)

    response = await client.post(
        f"/api/webhooks/{webhook.id}/test",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["webhook_id"] == webhook.id
    assert data["status"] in ["delivered", "failed"]


@pytest.mark.asyncio
async def test_hmac_signature_correct():
    """Test that HMAC signature computation is correct."""
    service = WebhookService()
    secret = "my_secret_key"
    payload = '{"event": "test", "data": {"test": true}}'

    signature = service.sign_payload(secret, payload)

    # Verify independently
    expected = hmac.new(
        secret.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    assert signature == expected


@pytest.mark.asyncio
async def test_webhook_not_found(client: AsyncClient, db_session: AsyncSession):
    """Test requesting a nonexistent webhook returns 404."""
    _, token = await _create_admin_user(db_session)

    response = await client.get(
        "/api/webhooks/99999",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404
