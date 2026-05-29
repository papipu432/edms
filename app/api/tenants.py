"""Multi-tenant API endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import require_role
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.tenant import TenantCreate, TenantResponse, TenantUpdate

router = APIRouter(tags=["tenants"])


@router.get("/api/tenants", response_model=list[TenantResponse])
async def list_tenants(
    _user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    """List all tenants."""
    result = await db.execute(select(Tenant))
    tenants = result.scalars().all()
    return tenants


@router.get("/api/tenants/{tenant_id}", response_model=TenantResponse)
async def get_tenant(
    tenant_id: int,
    _user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific tenant by ID."""
    result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = result.scalar_one_or_none()
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return tenant


@router.post("/api/tenants", response_model=TenantResponse, status_code=201)
async def create_tenant(
    data: TenantCreate,
    _user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    """Create a new tenant."""
    # Check slug uniqueness
    existing = await db.execute(select(Tenant).where(Tenant.slug == data.slug))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="Tenant slug already exists")

    tenant = Tenant(
        name=data.name,
        slug=data.slug,
        settings=data.settings,
        is_active=data.is_active,
    )
    db.add(tenant)
    await db.flush()
    await db.refresh(tenant)
    return tenant


@router.put("/api/tenants/{tenant_id}", response_model=TenantResponse)
async def update_tenant(
    tenant_id: int,
    data: TenantUpdate,
    _user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    """Update an existing tenant."""
    result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = result.scalar_one_or_none()
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(tenant, key, value)

    await db.flush()
    await db.refresh(tenant)
    return tenant


@router.delete("/api/tenants/{tenant_id}", status_code=204)
async def delete_tenant(
    tenant_id: int,
    _user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    """Delete a tenant."""
    result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = result.scalar_one_or_none()
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")

    await db.delete(tenant)
    await db.flush()
