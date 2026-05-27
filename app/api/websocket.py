import logging

from fastapi import APIRouter, Depends, Query, WebSocket, status
from jose import JWTError, jwt
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.notification import Notification
from app.models.user import User
from app.services.notifications import get_notification_manager

logger = logging.getLogger(__name__)

router = APIRouter(tags=["notifications"])


def _verify_ws_token(token: str) -> str | None:
    """Verify a JWT token and return the username, or None if invalid."""
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        username: str | None = payload.get("sub")
        return username
    except JWTError:
        return None


@router.websocket("/ws/notifications")
async def websocket_notifications(
    websocket: WebSocket,
    token: str = Query(...),
):
    """WebSocket endpoint for real-time notifications. Authenticate via token query param."""
    username = _verify_ws_token(token)
    if username is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # Look up user_id from username
    await websocket.accept()

    # Get a DB session to resolve the user
    from app.core.database import async_session

    async with async_session() as db:
        result = await db.execute(select(User).where(User.username == username))
        user = result.scalar_one_or_none()

    if user is None or not user.is_active:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    manager = get_notification_manager()
    manager.connect(user.id, websocket)

    try:
        while True:
            # Keep connection alive; handle ping/pong
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except Exception:
        pass
    finally:
        manager.disconnect(user.id, websocket)


@router.get("/api/notifications")
async def list_notifications(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List the current user's notifications with pagination."""
    query = (
        select(Notification)
        .where(
            (Notification.user_id == current_user.id)
            | (Notification.user_id.is_(None))
        )
        .order_by(Notification.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(query)
    notifications = result.scalars().all()

    return [
        {
            "id": n.id,
            "user_id": n.user_id,
            "notification_type": n.notification_type,
            "title": n.title,
            "message": n.message,
            "data": n.data_json,
            "is_read": n.is_read,
            "created_at": n.created_at.isoformat() if n.created_at else None,
        }
        for n in notifications
    ]


@router.post("/api/notifications/{notification_id}/read")
async def mark_notification_read(
    notification_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark a single notification as read."""
    result = await db.execute(
        select(Notification).where(Notification.id == notification_id)
    )
    notification = result.scalar_one_or_none()
    if notification is None:
        return {"detail": "Notification not found"}

    # Only allow marking notifications targeted to this user or broadcasts
    if notification.user_id is not None and notification.user_id != current_user.id:
        return {"detail": "Not authorized"}

    notification.is_read = True
    await db.flush()
    return {"id": notification.id, "is_read": True}


@router.post("/api/notifications/read-all")
async def mark_all_notifications_read(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark all of the current user's notifications as read."""
    await db.execute(
        update(Notification)
        .where(
            (Notification.user_id == current_user.id)
            | (Notification.user_id.is_(None))
        )
        .where(Notification.is_read == False)  # noqa: E712
        .values(is_read=True)
    )
    await db.flush()
    return {"detail": "All notifications marked as read"}


@router.get("/api/notifications/unread-count")
async def unread_count(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the count of unread notifications for the current user."""
    result = await db.execute(
        select(func.count(Notification.id)).where(
            (Notification.user_id == current_user.id)
            | (Notification.user_id.is_(None))
        ).where(Notification.is_read == False)  # noqa: E712
    )
    count = result.scalar() or 0
    return {"unread_count": count}
