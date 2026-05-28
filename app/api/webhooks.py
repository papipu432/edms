"""Webhook integrations API endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import require_role
from app.models.user import User
from app.models.webhook import WebhookConfig
from app.schemas.webhook import (
    WebhookCreate,
    WebhookResponse,
    WebhookTestResponse,
    WebhookUpdate,
)
from app.services.webhooks import WebhookService

router = APIRouter(tags=["webhooks"])

webhook_service = WebhookService()


@router.get("/api/webhooks", response_model=list[WebhookResponse])
async def list_webhooks(
    _user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    """List all webhook configurations."""
    result = await db.execute(select(WebhookConfig))
    webhooks = result.scalars().all()
    return webhooks


@router.get("/api/webhooks/{webhook_id}", response_model=WebhookResponse)
async def get_webhook(
    webhook_id: int,
    _user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific webhook by ID."""
    result = await db.execute(
        select(WebhookConfig).where(WebhookConfig.id == webhook_id)
    )
    webhook = result.scalar_one_or_none()
    if webhook is None:
        raise HTTPException(status_code=404, detail="Webhook not found")
    return webhook


@router.post("/api/webhooks", response_model=WebhookResponse, status_code=201)
async def create_webhook(
    data: WebhookCreate,
    _user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    """Create a new webhook configuration."""
    webhook = WebhookConfig(
        url=data.url,
        secret=data.secret,
        events=data.events,
        is_active=data.is_active,
        headers=data.headers,
    )
    db.add(webhook)
    await db.flush()
    await db.refresh(webhook)
    return webhook


@router.put("/api/webhooks/{webhook_id}", response_model=WebhookResponse)
async def update_webhook(
    webhook_id: int,
    data: WebhookUpdate,
    _user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    """Update an existing webhook configuration."""
    result = await db.execute(
        select(WebhookConfig).where(WebhookConfig.id == webhook_id)
    )
    webhook = result.scalar_one_or_none()
    if webhook is None:
        raise HTTPException(status_code=404, detail="Webhook not found")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(webhook, key, value)

    await db.flush()
    await db.refresh(webhook)
    return webhook


@router.delete("/api/webhooks/{webhook_id}", status_code=204)
async def delete_webhook(
    webhook_id: int,
    _user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    """Delete a webhook configuration."""
    result = await db.execute(
        select(WebhookConfig).where(WebhookConfig.id == webhook_id)
    )
    webhook = result.scalar_one_or_none()
    if webhook is None:
        raise HTTPException(status_code=404, detail="Webhook not found")

    await db.delete(webhook)
    await db.flush()


@router.post("/api/webhooks/{webhook_id}/test", response_model=WebhookTestResponse)
async def test_webhook(
    webhook_id: int,
    _user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    """Send a test payload to a webhook."""
    result = await db.execute(
        select(WebhookConfig).where(WebhookConfig.id == webhook_id)
    )
    webhook = result.scalar_one_or_none()
    if webhook is None:
        raise HTTPException(status_code=404, detail="Webhook not found")

    delivery = await webhook_service.test_webhook(db, webhook_id)
    return WebhookTestResponse(
        webhook_id=webhook_id,
        status=delivery.get("status", "unknown"),
        message=delivery.get("message", "Test payload sent"),
    )
