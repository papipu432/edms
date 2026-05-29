import json
import logging
from datetime import datetime, timezone

from fastapi import WebSocket
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification

logger = logging.getLogger(__name__)


class NotificationManager:
    """Singleton manager for WebSocket connections and notification delivery."""

    def __init__(self) -> None:
        self._connections: dict[str, list[WebSocket]] = {}

    def connect(self, user_id: str, websocket: WebSocket) -> None:
        """Register a WebSocket connection for a user."""
        if user_id not in self._connections:
            self._connections[user_id] = []
        self._connections[user_id].append(websocket)

    def disconnect(self, user_id: str, websocket: WebSocket) -> None:
        """Remove a WebSocket connection for a user."""
        if user_id in self._connections:
            self._connections[user_id] = [
                ws for ws in self._connections[user_id] if ws is not websocket
            ]
            if not self._connections[user_id]:
                del self._connections[user_id]

    async def broadcast(self, notification_dict: dict) -> None:
        """Send a notification to all connected clients."""
        message = json.dumps(notification_dict)
        disconnected: list[tuple[str, WebSocket]] = []
        for user_id, connections in self._connections.items():
            for ws in connections:
                try:
                    await ws.send_text(message)
                except Exception:
                    disconnected.append((user_id, ws))
        for user_id, ws in disconnected:
            self.disconnect(user_id, ws)

    async def send_to_user(self, user_id: str, notification_dict: dict) -> None:
        """Send a notification to a specific user's connections."""
        connections = self._connections.get(user_id, [])
        message = json.dumps(notification_dict)
        disconnected: list[WebSocket] = []
        for ws in connections:
            try:
                await ws.send_text(message)
            except Exception:
                disconnected.append(ws)
        for ws in disconnected:
            self.disconnect(user_id, ws)

    async def create_notification(
        self,
        db: AsyncSession,
        user_id: str | None,
        notification_type: str,
        title: str,
        message: str,
        data: dict | None = None,
    ) -> Notification:
        """Persist a notification to the database and send via WebSocket."""
        notification = Notification(
            user_id=user_id,
            notification_type=notification_type,
            title=title,
            message=message,
            data_json=data,
        )
        db.add(notification)
        await db.flush()

        notification_dict = {
            "id": notification.id,
            "user_id": user_id,
            "notification_type": notification_type,
            "title": title,
            "message": message,
            "data": data,
            "is_read": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        if user_id:
            await self.send_to_user(user_id, notification_dict)
        else:
            await self.broadcast(notification_dict)

        return notification

    async def notify_document_status(
        self,
        db: AsyncSession,
        doc_id: str,
        doc_name: str,
        status: str,
        user_id: str | None = None,
    ) -> Notification:
        """Create a notification for document status change."""
        title = f"Document Status: {status}"
        message = f"Document '{doc_name}' status changed to '{status}'."
        data = {"document_id": doc_id, "document_name": doc_name, "status": status}
        return await self.create_notification(
            db, user_id, "document_status", title, message, data
        )

    async def notify_lifecycle_alert(
        self,
        db: AsyncSession,
        lifecycle_id: str,
        alert_type: str,
        doc_name: str,
        user_id: str | None = None,
    ) -> Notification:
        """Create a notification for lifecycle alert."""
        title = f"Lifecycle Alert: {alert_type}"
        message = f"Lifecycle alert '{alert_type}' for document '{doc_name}'."
        data = {
            "lifecycle_id": lifecycle_id,
            "alert_type": alert_type,
            "document_name": doc_name,
        }
        return await self.create_notification(
            db, user_id, "lifecycle_alert", title, message, data
        )

    async def notify_ransomware_alert(
        self,
        db: AsyncSession,
        alert_data: dict,
    ) -> Notification:
        """Broadcast a ransomware alert notification to all connected users."""
        title = "Ransomware Alert"
        message = alert_data.get("message", "Potential ransomware activity detected.")
        return await self.create_notification(
            db, None, "ransomware_alert", title, message, alert_data
        )

    async def notify_backup_status(
        self,
        db: AsyncSession,
        job_id: str,
        status: str,
        target: str,
        user_id: str | None = None,
    ) -> Notification:
        """Create a notification for backup job status."""
        title = f"Backup {status.capitalize()}"
        message = f"Backup job to '{target}' {status}."
        data = {"job_id": job_id, "status": status, "target": target}
        return await self.create_notification(
            db, user_id, "backup_status", title, message, data
        )


# Module-level singleton
_notification_manager: NotificationManager | None = None


def get_notification_manager() -> NotificationManager:
    """Get or create the singleton NotificationManager instance."""
    global _notification_manager
    if _notification_manager is None:
        _notification_manager = NotificationManager()
    return _notification_manager
