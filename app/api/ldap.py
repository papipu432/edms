"""LDAP configuration and sync router."""
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user, require_role
from app.models.user import LdapConfig, LdapGroupRole, LdapSyncLog, User
from app.services.ldap_service import run_sync, test_connection

router = APIRouter(prefix="/ldap", tags=["ldap"])
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


# ── Schemas ───────────────────────────────────────────────────────────────────


class LdapConfigCreate(BaseModel):
    name: str
    server_url: str
    server_port: int = 389
    use_ssl: bool = False
    use_tls: bool = False
    connect_timeout: int = 10
    bind_dn: str | None = None
    bind_password: str | None = None
    base_dn: str
    user_search_filter: str = "(objectClass=person)"
    user_search_base: str | None = None
    group_search_filter: str = "(objectClass=groupOfNames)"
    group_search_base: str | None = None
    attr_username: str = "uid"
    attr_email: str = "mail"
    attr_display_name: str = "cn"
    sync_enabled: bool = False
    sync_create_users: bool = True
    sync_update_users: bool = True
    sync_disable_missing: bool = False
    default_role: str = "viewer"
    is_default: bool = False


class LdapGroupRoleCreate(BaseModel):
    ldap_group_dn: str
    role_code: str


# ── Pages ─────────────────────────────────────────────────────────────────────


@router.get("/config")
async def ldap_config_page(
    request: Request, _user: User = Depends(get_current_user)
):
    return templates.TemplateResponse(request, "ldap/config.html")


# ── API: Configs ──────────────────────────────────────────────────────────────


@router.get("/api/configs")
async def list_configs(
    _user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(LdapConfig))
    configs = result.scalars().all()
    return [
        {
            "id": c.id,
            "name": c.name,
            "server_url": c.server_url,
            "server_port": c.server_port,
            "base_dn": c.base_dn,
            "is_active": c.is_active,
            "is_default": c.is_default,
            "sync_enabled": c.sync_enabled,
        }
        for c in configs
    ]


@router.post("/api/configs", status_code=201)
async def create_config(
    data: LdapConfigCreate,
    _user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    config = LdapConfig(
        name=data.name,
        server_url=data.server_url,
        server_port=data.server_port,
        use_ssl=data.use_ssl,
        use_tls=data.use_tls,
        connect_timeout=data.connect_timeout,
        bind_dn=data.bind_dn,
        bind_password=data.bind_password,
        base_dn=data.base_dn,
        user_search_filter=data.user_search_filter,
        user_search_base=data.user_search_base,
        group_search_filter=data.group_search_filter,
        group_search_base=data.group_search_base,
        attr_username=data.attr_username,
        attr_email=data.attr_email,
        attr_display_name=data.attr_display_name,
        sync_enabled=data.sync_enabled,
        sync_create_users=data.sync_create_users,
        sync_update_users=data.sync_update_users,
        sync_disable_missing=data.sync_disable_missing,
        default_role=data.default_role,
        is_default=data.is_default,
    )
    db.add(config)
    await db.flush()
    await db.refresh(config)
    return {"id": config.id, "name": config.name}


@router.delete("/api/configs/{config_id}", status_code=204)
async def delete_config(
    config_id: str,
    _user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    config = await db.get(LdapConfig, config_id)
    if not config:
        raise HTTPException(status_code=404, detail="Config not found")
    await db.delete(config)
    await db.flush()


# ── API: Test Connection ──────────────────────────────────────────────────────


@router.post("/api/configs/{config_id}/test")
async def test_config_connection(
    config_id: str,
    _user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    config = await db.get(LdapConfig, config_id)
    if not config:
        raise HTTPException(status_code=404, detail="Config not found")
    config_dict = {
        "server_url": config.server_url,
        "server_port": config.server_port,
        "use_ssl": config.use_ssl,
        "use_tls": config.use_tls,
        "connect_timeout": config.connect_timeout,
        "bind_dn": config.bind_dn,
        "bind_password": config.bind_password,
        "base_dn": config.base_dn,
        "user_search_filter": config.user_search_filter,
    }
    result = test_connection(config_dict)
    return result


# ── API: Sync ─────────────────────────────────────────────────────────────────


@router.post("/api/configs/{config_id}/sync")
async def sync_config(
    config_id: str,
    _user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    config = await db.get(LdapConfig, config_id)
    if not config:
        raise HTTPException(status_code=404, detail="Config not found")
    config_dict = {
        "id": config.id,
        "server_url": config.server_url,
        "server_port": config.server_port,
        "use_ssl": config.use_ssl,
        "use_tls": config.use_tls,
        "bind_dn": config.bind_dn,
        "bind_password": config.bind_password,
        "base_dn": config.base_dn,
        "user_search_filter": config.user_search_filter,
        "user_search_base": config.user_search_base,
        "attr_username": config.attr_username,
        "attr_email": config.attr_email,
        "attr_display_name": config.attr_display_name,
        "sync_create_users": config.sync_create_users,
        "sync_update_users": config.sync_update_users,
        "sync_disable_missing": config.sync_disable_missing,
        "default_role": config.default_role,
    }
    result = await run_sync(config_dict, db)
    return result


@router.get("/api/configs/{config_id}/logs")
async def list_sync_logs(
    config_id: str,
    _user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(LdapSyncLog)
        .where(LdapSyncLog.config_id == config_id)
        .order_by(LdapSyncLog.started_at.desc())
        .limit(20)
    )
    logs = result.scalars().all()
    return [
        {
            "id": entry.id,
            "status": entry.status,
            "started_at": entry.started_at.isoformat() if entry.started_at else None,
            "finished_at": entry.finished_at.isoformat() if entry.finished_at else None,
            "users_found": entry.users_found,
            "users_created": entry.users_created,
            "users_updated": entry.users_updated,
            "errors": entry.errors,
        }
        for entry in logs
    ]


# ── API: Group-Role Mappings ─────────────────────────────────────────────────


@router.get("/api/configs/{config_id}/group-roles")
async def list_group_roles(
    config_id: str,
    _user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(LdapGroupRole).where(LdapGroupRole.config_id == config_id)
    )
    mappings = result.scalars().all()
    return [
        {
            "id": m.id,
            "ldap_group_dn": m.ldap_group_dn,
            "role_code": m.role_code,
            "is_active": m.is_active,
        }
        for m in mappings
    ]


@router.post("/api/configs/{config_id}/group-roles", status_code=201)
async def create_group_role(
    config_id: str,
    data: LdapGroupRoleCreate,
    _user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    config = await db.get(LdapConfig, config_id)
    if not config:
        raise HTTPException(status_code=404, detail="Config not found")
    mapping = LdapGroupRole(
        config_id=config_id,
        ldap_group_dn=data.ldap_group_dn,
        role_code=data.role_code,
    )
    db.add(mapping)
    await db.flush()
    await db.refresh(mapping)
    return {"id": mapping.id, "ldap_group_dn": mapping.ldap_group_dn}


@router.delete("/api/configs/{config_id}/group-roles/{mapping_id}", status_code=204)
async def delete_group_role(
    config_id: str,
    mapping_id: str,
    _user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(LdapGroupRole).where(
            LdapGroupRole.id == mapping_id,
            LdapGroupRole.config_id == config_id,
        )
    )
    mapping = result.scalar_one_or_none()
    if not mapping:
        raise HTTPException(status_code=404, detail="Mapping not found")
    await db.delete(mapping)
    await db.flush()
