"""RBAC management router - roles and permissions CRUD."""
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user, require_role
from app.models.user import Permission, Role, RolePermission, User

router = APIRouter(prefix="/rbac", tags=["rbac"])
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


# ── Schemas ───────────────────────────────────────────────────────────────────


class RoleCreate(BaseModel):
    code: str
    name: str
    description: str | None = None


class PermissionCreate(BaseModel):
    resource: str
    action: str
    description: str | None = None


class RolePermissionAssign(BaseModel):
    permission_id: str


# ── Pages ─────────────────────────────────────────────────────────────────────


@router.get("/roles")
async def roles_page(request: Request, _user: User = Depends(get_current_user)):
    return templates.TemplateResponse(request, "rbac/roles.html")


@router.get("/permissions")
async def permissions_page(
    request: Request, _user: User = Depends(get_current_user)
):
    return templates.TemplateResponse(request, "rbac/permissions.html")


# ── API: Roles ────────────────────────────────────────────────────────────────


@router.get("/api/roles")
async def list_roles(
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Role).order_by(Role.code))
    roles = result.scalars().all()
    return [
        {
            "id": r.id,
            "code": r.code,
            "name": r.name,
            "description": r.description,
            "is_system": r.is_system,
            "is_active": r.is_active,
            "permissions": [
                {
                    "id": rp.permission.id,
                    "resource": rp.permission.resource,
                    "action": rp.permission.action,
                }
                for rp in r.permissions
                if rp.permission
            ],
        }
        for r in roles
    ]


@router.post("/api/roles", status_code=201)
async def create_role(
    data: RoleCreate,
    _user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    role = Role(code=data.code, name=data.name, description=data.description)
    db.add(role)
    await db.flush()
    await db.refresh(role)
    return {"id": role.id, "code": role.code, "name": role.name}


@router.put("/api/roles/{role_id}")
async def update_role(
    role_id: str,
    data: RoleCreate,
    _user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    role = await db.get(Role, role_id)
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    if role.is_system:
        raise HTTPException(status_code=400, detail="Cannot modify system role")
    role.code = data.code
    role.name = data.name
    role.description = data.description
    await db.flush()
    return {"id": role.id, "code": role.code, "name": role.name}


@router.delete("/api/roles/{role_id}", status_code=204)
async def delete_role(
    role_id: str,
    _user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    role = await db.get(Role, role_id)
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    if role.is_system:
        raise HTTPException(status_code=400, detail="Cannot delete system role")
    await db.delete(role)
    await db.flush()


@router.post("/api/roles/{role_id}/permissions", status_code=201)
async def assign_permission_to_role(
    role_id: str,
    data: RolePermissionAssign,
    _user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    role = await db.get(Role, role_id)
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    perm = await db.get(Permission, data.permission_id)
    if not perm:
        raise HTTPException(status_code=404, detail="Permission not found")

    # Check if already assigned
    result = await db.execute(
        select(RolePermission).where(
            RolePermission.role_id == role_id,
            RolePermission.permission_id == data.permission_id,
        )
    )
    if result.scalar_one_or_none():
        return {"detail": "Already assigned"}

    rp = RolePermission(role_id=role_id, permission_id=data.permission_id)
    db.add(rp)
    await db.flush()
    return {"id": rp.id, "role_id": role_id, "permission_id": data.permission_id}


@router.delete("/api/roles/{role_id}/permissions/{permission_id}", status_code=204)
async def remove_permission_from_role(
    role_id: str,
    permission_id: str,
    _user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(RolePermission).where(
            RolePermission.role_id == role_id,
            RolePermission.permission_id == permission_id,
        )
    )
    rp = result.scalar_one_or_none()
    if not rp:
        raise HTTPException(status_code=404, detail="Role-permission mapping not found")
    await db.delete(rp)
    await db.flush()


# ── API: Permissions ──────────────────────────────────────────────────────────


@router.get("/api/permissions")
async def list_permissions(
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Permission).order_by(Permission.resource, Permission.action)
    )
    perms = result.scalars().all()
    return [
        {
            "id": p.id,
            "resource": p.resource,
            "action": p.action,
            "description": p.description,
        }
        for p in perms
    ]


@router.post("/api/permissions", status_code=201)
async def create_permission(
    data: PermissionCreate,
    _user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    perm = Permission(
        resource=data.resource, action=data.action, description=data.description
    )
    db.add(perm)
    await db.flush()
    await db.refresh(perm)
    return {"id": perm.id, "resource": perm.resource, "action": perm.action}


@router.delete("/api/permissions/{permission_id}", status_code=204)
async def delete_permission(
    permission_id: str,
    _user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    perm = await db.get(Permission, permission_id)
    if not perm:
        raise HTTPException(status_code=404, detail="Permission not found")
    await db.delete(perm)
    await db.flush()
