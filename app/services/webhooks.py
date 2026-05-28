"""Webhook integration service."""

import hashlib
import hmac
import json
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.webhook import WebhookConfig

logger = logging.getLogger(__name__)

VALID_EVENTS = [
    "document.uploaded",
    "document.approved",
    "document.expired",
    "lifecycle.alert",
    "security.alert",
    "backup.completed",
]


class WebhookService:
    """Manages webhook firing with HMAC signing and retry logic."""

    def sign_payload(self, secret: str, payload: str) -> str:
        """Sign a payload with HMAC-SHA256."""
        return hmac.HMAC(
            secret.encode("utf-8"),
            payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    async def fire_event(
        self, db: AsyncSession, event_type: str, payload: dict
    ) -> list[dict]:
        """Fire an event to all active webhooks subscribed to it."""
        result = await db.execute(
            select(WebhookConfig).where(WebhookConfig.is_active.is_(True))
        )
        webhooks = result.scalars().all()
        results = []

        for webhook in webhooks:
            events = webhook.events or []
            if event_type not in events:
                continue

            delivery_result = await self._deliver(webhook, event_type, payload)
            results.append(delivery_result)

        return results

    async def _deliver(
        self, webhook: WebhookConfig, event_type: str, payload: dict
    ) -> dict:
        """Deliver a webhook payload with retries."""
        body = json.dumps({"event": event_type, "data": payload})
        signature = self.sign_payload(webhook.secret, body)

        headers = {
            "Content-Type": "application/json",
            "X-Webhook-Signature": signature,
            "X-Webhook-Event": event_type,
        }
        if webhook.headers:
            headers.update(webhook.headers)

        max_retries = 3
        delays = [1, 2, 4]

        for attempt in range(max_retries):
            try:
                import httpx

                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.post(
                        webhook.url, content=body, headers=headers
                    )
                    if response.status_code < 400:
                        return {
                            "webhook_id": webhook.id,
                            "status": "delivered",
                            "status_code": response.status_code,
                        }
                    logger.warning(
                        "Webhook %d returned %d on attempt %d",
                        webhook.id,
                        response.status_code,
                        attempt + 1,
                    )
            except Exception as e:
                logger.warning(
                    "Webhook %d delivery failed on attempt %d: %s",
                    webhook.id,
                    attempt + 1,
                    str(e),
                )

            if attempt < max_retries - 1:
                import asyncio

                await asyncio.sleep(delays[attempt])

        return {"webhook_id": webhook.id, "status": "failed", "message": "Max retries exceeded"}

    async def test_webhook(self, db: AsyncSession, webhook_id: int) -> dict:
        """Send a test payload to a webhook."""
        result = await db.execute(
            select(WebhookConfig).where(WebhookConfig.id == webhook_id)
        )
        webhook = result.scalar_one_or_none()
        if webhook is None:
            return {"status": "error", "message": "Webhook not found"}

        test_payload = {"test": True, "message": "This is a test webhook delivery"}
        delivery = await self._deliver(webhook, "test", test_payload)
        return delivery
