from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.delegation import Delegation, DelegationScopeType
from app.models.user import User
from app.schemas.delegation import DelegationCreate, DelegationResponse

router = APIRouter(tags=["delegations"])


@router.post(
    "/api/delegations",
    response_model=DelegationResponse,
    status_code=201,
)
async def create_delegation(
    data: DelegationCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a delegation of approval authority."""
    # Verify delegate user exists
    delegate = await db.get(User, data.delegate_id)
    if not delegate:
        raise HTTPException(status_code=404, detail="Delegate user not found")

    delegation = Delegation(
        delegator_id=current_user.id,
        delegate_id=data.delegate_id,
        start_date=data.start_date,
        end_date=data.end_date,
        scope_type=DelegationScopeType(data.scope_type),
        scope_folder_id=data.scope_folder_id,
        is_active=True,
    )
    db.add(delegation)
    await db.flush()
    await db.refresh(delegation)

    return DelegationResponse(
        id=delegation.id,
        delegator_id=delegation.delegator_id,
        delegator_username=current_user.username,
        delegate_id=delegation.delegate_id,
        delegate_username=delegate.username,
        start_date=delegation.start_date,
        end_date=delegation.end_date,
        scope_type=delegation.scope_type.value,
        scope_folder_id=delegation.scope_folder_id,
        is_active=delegation.is_active,
        created_at=delegation.created_at,
    )


@router.get(
    "/api/delegations",
    response_model=list[DelegationResponse],
)
async def list_delegations(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List active delegations for current user (as delegator or delegate)."""
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(Delegation).where(
            and_(
                Delegation.is_active == True,  # noqa: E712
                Delegation.start_date <= now,
                Delegation.end_date >= now,
                or_(
                    Delegation.delegator_id == current_user.id,
                    Delegation.delegate_id == current_user.id,
                ),
            )
        )
    )
    delegations = list(result.scalars().all())

    responses = []
    for d in delegations:
        delegator = await db.get(User, d.delegator_id)
        delegate = await db.get(User, d.delegate_id)
        responses.append(
            DelegationResponse(
                id=d.id,
                delegator_id=d.delegator_id,
                delegator_username=delegator.username if delegator else None,
                delegate_id=d.delegate_id,
                delegate_username=delegate.username if delegate else None,
                start_date=d.start_date,
                end_date=d.end_date,
                scope_type=d.scope_type.value,
                scope_folder_id=d.scope_folder_id,
                is_active=d.is_active,
                created_at=d.created_at,
            )
        )
    return responses


@router.delete(
    "/api/delegations/{delegation_id}",
    status_code=204,
)
async def revoke_delegation(
    delegation_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Revoke a delegation - only delegator or admin can revoke."""
    delegation = await db.get(Delegation, delegation_id)
    if not delegation:
        raise HTTPException(status_code=404, detail="Delegation not found")

    is_admin = "admin" in current_user.role_codes
    if delegation.delegator_id != current_user.id and not is_admin:
        raise HTTPException(status_code=403, detail="Not authorized to revoke this delegation")

    delegation.is_active = False
    await db.flush()


@router.get(
    "/api/delegations/active-for/{user_id}",
    response_model=list[DelegationResponse],
)
async def get_active_delegations_for_user(
    user_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Check if a user has active delegations - used internally by approval system."""
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(Delegation).where(
            and_(
                Delegation.delegate_id == user_id,
                Delegation.is_active == True,  # noqa: E712
                Delegation.start_date <= now,
                Delegation.end_date >= now,
            )
        )
    )
    delegations = list(result.scalars().all())

    responses = []
    for d in delegations:
        delegator = await db.get(User, d.delegator_id)
        delegate = await db.get(User, d.delegate_id)
        responses.append(
            DelegationResponse(
                id=d.id,
                delegator_id=d.delegator_id,
                delegator_username=delegator.username if delegator else None,
                delegate_id=d.delegate_id,
                delegate_username=delegate.username if delegate else None,
                start_date=d.start_date,
                end_date=d.end_date,
                scope_type=d.scope_type.value,
                scope_folder_id=d.scope_folder_id,
                is_active=d.is_active,
                created_at=d.created_at,
            )
        )
    return responses
