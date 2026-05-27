from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import role_required
from app.models.user import FolderAssignment, Role, RoleName, User
from app.schemas.user import (
    FolderAssignmentCreate,
    FolderAssignmentResponse,
    RoleAssign,
    UserResponse,
)

router = APIRouter(prefix="/api/users", tags=["users"])

admin_required = role_required(["admin"])


@router.get("", response_model=list[UserResponse])
async def list_users(
    _current_user: User = Depends(admin_required),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User))
    users = result.scalars().all()
    return [
        UserResponse(
            id=u.id,
            username=u.username,
            email=u.email,
            is_active=u.is_active,
            roles=[r.name.value for r in u.roles],
            created_at=u.created_at,
            updated_at=u.updated_at,
        )
        for u in users
    ]


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: int,
    _current_user: User = Depends(admin_required),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return UserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        is_active=user.is_active,
        roles=[r.name.value for r in user.roles],
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


@router.post("/{user_id}/roles", response_model=UserResponse)
async def assign_role(
    user_id: int,
    role_data: RoleAssign,
    _current_user: User = Depends(admin_required),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    # Validate role name
    try:
        role_name_enum = RoleName(role_data.role_name)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid role name")

    result = await db.execute(select(Role).where(Role.name == role_name_enum))
    role = result.scalar_one_or_none()
    if role is None:
        raise HTTPException(status_code=404, detail="Role not found")

    # Check if user already has this role
    if role not in user.roles:
        user.roles.append(role)
        await db.flush()
        await db.refresh(user)

    return UserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        is_active=user.is_active,
        roles=[r.name.value for r in user.roles],
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


@router.delete("/{user_id}/roles/{role_name}", response_model=UserResponse)
async def remove_role(
    user_id: int,
    role_name: str,
    _current_user: User = Depends(admin_required),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    try:
        role_name_enum = RoleName(role_name)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid role name")

    result = await db.execute(select(Role).where(Role.name == role_name_enum))
    role = result.scalar_one_or_none()
    if role is None:
        raise HTTPException(status_code=404, detail="Role not found")

    if role in user.roles:
        user.roles.remove(role)
        await db.flush()
        await db.refresh(user)

    return UserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        is_active=user.is_active,
        roles=[r.name.value for r in user.roles],
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


@router.post("/{user_id}/folders", response_model=FolderAssignmentResponse)
async def assign_folder(
    user_id: int,
    folder_data: FolderAssignmentCreate,
    _current_user: User = Depends(admin_required),
    db: AsyncSession = Depends(get_db),
):
    # Verify user exists
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    # Validate role name
    try:
        role_name_enum = RoleName(folder_data.role_name)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid role name")

    result = await db.execute(select(Role).where(Role.name == role_name_enum))
    role = result.scalar_one_or_none()
    if role is None:
        raise HTTPException(status_code=404, detail="Role not found")

    assignment = FolderAssignment(
        user_id=user_id,
        folder_path=folder_data.folder_path,
        role_id=role.id,
    )
    db.add(assignment)
    await db.flush()
    await db.refresh(assignment)

    return FolderAssignmentResponse(
        id=assignment.id,
        user_id=assignment.user_id,
        folder_path=assignment.folder_path,
        role_name=assignment.role.name.value,
        granted_at=assignment.granted_at,
    )


@router.get("/{user_id}/folders", response_model=list[FolderAssignmentResponse])
async def list_folder_assignments(
    user_id: int,
    _current_user: User = Depends(admin_required),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(FolderAssignment).where(FolderAssignment.user_id == user_id)
    )
    assignments = result.scalars().all()
    return [
        FolderAssignmentResponse(
            id=a.id,
            user_id=a.user_id,
            folder_path=a.folder_path,
            role_name=a.role.name.value,
            granted_at=a.granted_at,
        )
        for a in assignments
    ]


@router.delete(
    "/{user_id}/folders/{assignment_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def remove_folder_assignment(
    user_id: int,
    assignment_id: int,
    _current_user: User = Depends(admin_required),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(FolderAssignment).where(
            FolderAssignment.id == assignment_id,
            FolderAssignment.user_id == user_id,
        )
    )
    assignment = result.scalar_one_or_none()
    if assignment is None:
        raise HTTPException(status_code=404, detail="Folder assignment not found")

    await db.delete(assignment)
    await db.flush()
