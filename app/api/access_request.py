"""Access request workflow API router."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.access_request import AccessRequestCreate, AccessRequestResponse
from app.services.access_request import AccessRequestService

router = APIRouter(tags=["access-requests"])

access_request_service = AccessRequestService()


async def _require_admin(user: User) -> None:
    """Check that the current user has admin role."""
    if "admin" not in user.role_codes:
        raise HTTPException(status_code=403, detail="Admin role required")


@router.post("/api/request-access", response_model=AccessRequestResponse)
async def create_access_request(
    request: AccessRequestCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new access request (any authenticated user)."""
    if request.resource_type not in ("document", "group"):
        raise HTTPException(
            status_code=400,
            detail="resource_type must be 'document' or 'group'",
        )

    access_request = await access_request_service.create_request(
        db=db,
        requester_id=current_user.id,
        resource_type=request.resource_type,
        resource_id=request.resource_id,
        reason=request.reason,
    )
    return access_request


@router.get("/api/access-requests", response_model=list[AccessRequestResponse])
async def list_pending_requests(
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all pending access requests (admin only)."""
    await _require_admin(current_user)
    return await access_request_service.list_pending(db, limit=limit, offset=offset)


@router.get("/api/access-requests/mine", response_model=list[AccessRequestResponse])
async def list_my_requests(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List the current user's access requests."""
    return await access_request_service.list_user_requests(db, current_user.id)


@router.post(
    "/api/access-requests/{request_id}/approve",
    response_model=AccessRequestResponse,
)
async def approve_request(
    request_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Approve an access request (admin only)."""
    await _require_admin(current_user)
    result = await access_request_service.approve_request(
        db, request_id, current_user.id
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Access request not found")
    return result


@router.post(
    "/api/access-requests/{request_id}/deny",
    response_model=AccessRequestResponse,
)
async def deny_request(
    request_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Deny an access request (admin only)."""
    await _require_admin(current_user)
    result = await access_request_service.deny_request(
        db, request_id, current_user.id
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Access request not found")
    return result
