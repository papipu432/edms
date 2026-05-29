"""Geo-fencing API router for managing geo-fence rules."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.geofence import GeoFenceRule
from app.models.user import User

router = APIRouter(tags=["geofence"])


class GeoFenceRuleCreate(BaseModel):
    scope: str = "global"
    scope_id: int | None = None
    allowed_ip_ranges: list[str] | None = None
    denied_ip_ranges: list[str] | None = None
    allowed_countries: list[str] | None = None
    denied_countries: list[str] | None = None
    action: str = "allow"
    enabled: bool = True


class GeoFenceRuleUpdate(BaseModel):
    scope: str | None = None
    scope_id: int | None = None
    allowed_ip_ranges: list[str] | None = None
    denied_ip_ranges: list[str] | None = None
    allowed_countries: list[str] | None = None
    denied_countries: list[str] | None = None
    action: str | None = None
    enabled: bool | None = None


class GeoFenceRuleResponse(BaseModel):
    id: int
    scope: str
    scope_id: int | None
    allowed_ip_ranges: list[str] | None
    denied_ip_ranges: list[str] | None
    allowed_countries: list[str] | None
    denied_countries: list[str] | None
    action: str
    enabled: bool


async def _require_admin(user: User) -> None:
    """Check that the current user has admin role."""
    if "admin" not in user.role_codes:
        raise HTTPException(status_code=403, detail="Admin role required")


@router.get("/api/geofence/rules", response_model=list[GeoFenceRuleResponse])
async def list_geofence_rules(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all geo-fence rules (admin only)."""
    await _require_admin(current_user)

    result = await db.execute(select(GeoFenceRule))
    rules = result.scalars().all()

    return [
        GeoFenceRuleResponse(
            id=r.id,
            scope=r.scope,
            scope_id=r.scope_id,
            allowed_ip_ranges=r.allowed_ip_ranges,
            denied_ip_ranges=r.denied_ip_ranges,
            allowed_countries=r.allowed_countries,
            denied_countries=r.denied_countries,
            action=r.action,
            enabled=r.enabled,
        )
        for r in rules
    ]


@router.post("/api/geofence/rules", response_model=GeoFenceRuleResponse)
async def create_geofence_rule(
    rule_data: GeoFenceRuleCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new geo-fence rule (admin only)."""
    await _require_admin(current_user)

    if rule_data.scope not in ("global", "group", "document"):
        raise HTTPException(
            status_code=400,
            detail="Scope must be one of: global, group, document",
        )

    rule = GeoFenceRule(
        scope=rule_data.scope,
        scope_id=rule_data.scope_id,
        allowed_ip_ranges=rule_data.allowed_ip_ranges,
        denied_ip_ranges=rule_data.denied_ip_ranges,
        allowed_countries=rule_data.allowed_countries,
        denied_countries=rule_data.denied_countries,
        action=rule_data.action,
        enabled=rule_data.enabled,
    )
    db.add(rule)
    await db.flush()
    await db.refresh(rule)

    return GeoFenceRuleResponse(
        id=rule.id,
        scope=rule.scope,
        scope_id=rule.scope_id,
        allowed_ip_ranges=rule.allowed_ip_ranges,
        denied_ip_ranges=rule.denied_ip_ranges,
        allowed_countries=rule.allowed_countries,
        denied_countries=rule.denied_countries,
        action=rule.action,
        enabled=rule.enabled,
    )


@router.put("/api/geofence/rules/{rule_id}", response_model=GeoFenceRuleResponse)
async def update_geofence_rule(
    rule_id: int,
    rule_data: GeoFenceRuleUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update a geo-fence rule (admin only)."""
    await _require_admin(current_user)

    result = await db.execute(
        select(GeoFenceRule).where(GeoFenceRule.id == rule_id)
    )
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")

    if rule_data.scope is not None:
        rule.scope = rule_data.scope
    if rule_data.scope_id is not None:
        rule.scope_id = rule_data.scope_id
    if rule_data.allowed_ip_ranges is not None:
        rule.allowed_ip_ranges = rule_data.allowed_ip_ranges
    if rule_data.denied_ip_ranges is not None:
        rule.denied_ip_ranges = rule_data.denied_ip_ranges
    if rule_data.allowed_countries is not None:
        rule.allowed_countries = rule_data.allowed_countries
    if rule_data.denied_countries is not None:
        rule.denied_countries = rule_data.denied_countries
    if rule_data.action is not None:
        rule.action = rule_data.action
    if rule_data.enabled is not None:
        rule.enabled = rule_data.enabled

    await db.flush()
    await db.refresh(rule)

    return GeoFenceRuleResponse(
        id=rule.id,
        scope=rule.scope,
        scope_id=rule.scope_id,
        allowed_ip_ranges=rule.allowed_ip_ranges,
        denied_ip_ranges=rule.denied_ip_ranges,
        allowed_countries=rule.allowed_countries,
        denied_countries=rule.denied_countries,
        action=rule.action,
        enabled=rule.enabled,
    )


@router.delete("/api/geofence/rules/{rule_id}")
async def delete_geofence_rule(
    rule_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a geo-fence rule (admin only)."""
    await _require_admin(current_user)

    result = await db.execute(
        select(GeoFenceRule).where(GeoFenceRule.id == rule_id)
    )
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")

    await db.delete(rule)
    return {"detail": "Rule deleted"}
