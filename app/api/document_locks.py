from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.document import Document
from app.models.document_lock import DocumentLock
from app.models.user import User
from app.schemas.document_lock import LockCreate, LockResponse, LockStatusResponse

router = APIRouter(tags=["document-locks"])

# NOTE: Document locks are advisory-only. Document mutation endpoints (upload,
# update metadata, delete) do not currently check lock status before allowing
# writes. Enforcement at the mutation layer can be added incrementally by
# consulting _get_active_lock before permitting changes.


async def _get_active_lock(document_id: int, db: AsyncSession) -> DocumentLock | None:
    """Get the active (non-expired) lock for a document, cleaning up expired ones."""
    result = await db.execute(
        select(DocumentLock).where(DocumentLock.document_id == document_id)
    )
    lock = result.scalar_one_or_none()
    if lock:
        now = datetime.utcnow()
        expires = lock.expires_at.replace(tzinfo=None) if lock.expires_at.tzinfo else lock.expires_at
        if expires < now:
            # Lock has expired, remove it
            await db.delete(lock)
            await db.flush()
            return None
    return lock


async def _build_lock_response(lock: DocumentLock, db: AsyncSession) -> LockResponse:
    """Build a LockResponse with username populated."""
    user = await db.get(User, lock.user_id)
    username = user.username if user else "unknown"
    now = datetime.utcnow()
    expires = lock.expires_at.replace(tzinfo=None) if lock.expires_at.tzinfo else lock.expires_at
    is_expired = expires < now
    return LockResponse(
        id=lock.id,
        document_id=lock.document_id,
        user_id=lock.user_id,
        username=username,
        locked_at=lock.locked_at,
        expires_at=lock.expires_at,
        reason=lock.reason,
        is_expired=is_expired,
    )


@router.post(
    "/api/documents/{document_id}/lock",
    response_model=LockResponse,
    status_code=201,
)
async def lock_document(
    document_id: int,
    data: LockCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    document = await db.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    existing_lock = await _get_active_lock(document_id, db)
    if existing_lock:
        if existing_lock.user_id == current_user.id:
            # User already holds the lock, return it
            return await _build_lock_response(existing_lock, db)
        raise HTTPException(
            status_code=409,
            detail="Document is already locked by another user",
        )

    now = datetime.utcnow()
    lock = DocumentLock(
        document_id=document_id,
        user_id=current_user.id,
        locked_at=now,
        expires_at=now + timedelta(hours=data.duration_hours),
        reason=data.reason,
    )
    db.add(lock)
    await db.flush()
    await db.refresh(lock)
    return await _build_lock_response(lock, db)


@router.delete(
    "/api/documents/{document_id}/lock",
    status_code=204,
)
async def unlock_document(
    document_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(DocumentLock).where(DocumentLock.document_id == document_id)
    )
    lock = result.scalar_one_or_none()
    if not lock:
        raise HTTPException(status_code=404, detail="Document is not locked")

    # Allow unlock by owner or admin
    is_admin = "admin" in current_user.role_codes
    if lock.user_id != current_user.id and not is_admin:
        raise HTTPException(status_code=403, detail="Cannot unlock another user's lock")

    await db.delete(lock)
    await db.flush()


@router.get(
    "/api/documents/{document_id}/lock",
    response_model=LockStatusResponse,
)
async def get_lock_status(
    document_id: int,
    db: AsyncSession = Depends(get_db),
):
    document = await db.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    lock = await _get_active_lock(document_id, db)
    if not lock:
        return LockStatusResponse(is_locked=False, lock=None)

    lock_response = await _build_lock_response(lock, db)
    return LockStatusResponse(is_locked=True, lock=lock_response)
