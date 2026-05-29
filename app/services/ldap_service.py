"""LDAP service for EDMS - async adapted from OrgRBAC."""
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import LdapConfig, LdapSyncLog, Role, User, UserRole

log = logging.getLogger("edms.ldap_service")


def test_connection(config: dict) -> dict:
    """Test LDAP connection with given config dict."""
    try:
        import ldap3

        server = ldap3.Server(
            config["server_url"],
            port=config["server_port"],
            use_ssl=config.get("use_ssl", False),
            get_info=ldap3.ALL,
            connect_timeout=config.get("connect_timeout", 10),
        )
        conn = ldap3.Connection(
            server,
            user=config.get("bind_dn"),
            password=config.get("bind_password"),
            auto_bind=(
                ldap3.AUTO_BIND_TLS_BEFORE_BIND if config.get("use_tls") else True
            ),
        )
        conn.search(
            search_base=config["base_dn"],
            search_filter=config.get("user_search_filter", "(objectClass=person)"),
            attributes=["cn"],
            size_limit=1,
        )
        detail = f"Connected. Entries found (limited to 1): {len(conn.entries)}"
        conn.unbind()
        return {"ok": True, "detail": detail}
    except ImportError:
        return {
            "ok": False,
            "detail": "ldap3 package not installed. Install with: pip install ldap3",
        }
    except Exception as e:
        return {"ok": False, "detail": str(e)}


async def run_sync(config_dict: dict, db: AsyncSession) -> dict:
    """Run LDAP sync using async session."""
    sync_log = LdapSyncLog(
        config_id=config_dict["id"],
        status="running",
    )
    db.add(sync_log)
    await db.flush()
    await db.refresh(sync_log)
    sync_id = sync_log.id

    try:
        import ldap3

        server = ldap3.Server(
            config_dict["server_url"],
            port=config_dict["server_port"],
            use_ssl=config_dict.get("use_ssl", False),
        )
        conn = ldap3.Connection(
            server,
            user=config_dict.get("bind_dn"),
            password=config_dict.get("bind_password"),
            auto_bind=(
                ldap3.AUTO_BIND_TLS_BEFORE_BIND
                if config_dict.get("use_tls")
                else True
            ),
        )

        search_base = (
            config_dict.get("user_search_base") or config_dict["base_dn"]
        )
        attrs = [
            config_dict.get("attr_username", "uid"),
            config_dict.get("attr_email", "mail"),
            config_dict.get("attr_display_name", "cn"),
        ]
        conn.search(
            search_base=search_base,
            search_filter=config_dict.get(
                "user_search_filter", "(objectClass=person)"
            ),
            attributes=attrs,
            paged_size=1000,
        )

        users_found = len(conn.entries)
        created = updated = disabled = errors = 0

        result = await db.execute(select(User))
        existing_users = result.scalars().all()
        existing_map = {u.username: u for u in existing_users}
        ldap_names: set[str] = set()

        for entry in conn.entries:
            try:
                username = str(
                    entry[config_dict.get("attr_username", "uid")]
                )
                if not username:
                    continue
                ldap_names.add(username)
                email = str(entry[config_dict.get("attr_email", "mail")])
                display_name = str(
                    entry[config_dict.get("attr_display_name", "cn")]
                )

                if username in existing_map:
                    if config_dict.get("sync_update_users", True):
                        user = existing_map[username]
                        user.email = email or None
                        user.display_name = display_name
                        updated += 1
                else:
                    if config_dict.get("sync_create_users", True):
                        new_user = User(
                            username=username,
                            display_name=display_name,
                            email=email or None,
                            is_active=True,
                            is_ldap=True,
                        )
                        db.add(new_user)
                        await db.flush()

                        # Assign default role
                        default_role_code = config_dict.get("default_role", "viewer")
                        role_result = await db.execute(
                            select(Role).where(Role.code == default_role_code)
                        )
                        role = role_result.scalar_one_or_none()
                        if role:
                            db.add(UserRole(user_id=new_user.id, role_id=role.id))
                        created += 1
            except Exception as e:
                errors += 1
                log.error("LDAP entry error: %s", e)

        if config_dict.get("sync_disable_missing", False):
            for username, user in existing_map.items():
                if username not in ldap_names and user.is_active and user.is_ldap:
                    user.is_active = False
                    disabled += 1

        sync_log.status = "completed"
        sync_log.users_found = users_found
        sync_log.users_created = created
        sync_log.users_updated = updated
        sync_log.users_disabled = disabled
        sync_log.errors = errors
        await db.flush()
        conn.unbind()

        return {
            "ok": True,
            "sync_id": sync_id,
            "users_found": users_found,
            "users_created": created,
            "users_updated": updated,
            "users_disabled": disabled,
            "errors": errors,
        }
    except ImportError:
        sync_log.status = "failed"
        sync_log.error_detail = "ldap3 not installed"
        await db.flush()
        return {"ok": False, "detail": "ldap3 package not installed"}
    except Exception as e:
        sync_log.status = "failed"
        sync_log.error_detail = str(e)
        await db.flush()
        return {"ok": False, "detail": str(e)}


async def authenticate_ldap(
    username: str, password: str, db: AsyncSession
) -> User | None:
    """Authenticate user via LDAP. Returns User object or None."""
    result = await db.execute(
        select(LdapConfig).where(
            LdapConfig.is_active == True,  # noqa: E712
            LdapConfig.is_default == True,  # noqa: E712
        )
    )
    config = result.scalar_one_or_none()
    if not config:
        return None

    try:
        import ldap3
        from ldap3.utils.conv import escape_filter_chars

        server = ldap3.Server(
            config.server_url, port=config.server_port, use_ssl=config.use_ssl
        )
        search_base = config.user_search_base or config.base_dn
        safe_username = escape_filter_chars(username)
        user_dn = f"{config.attr_username}={safe_username},{search_base}"
        conn = ldap3.Connection(
            server,
            user=user_dn,
            password=password,
            auto_bind=(
                ldap3.AUTO_BIND_TLS_BEFORE_BIND if config.use_tls else True
            ),
        )

        conn.search(
            search_base=search_base,
            search_filter=f"({config.attr_username}={safe_username})",
            attributes=[
                config.attr_email,
                config.attr_display_name,
            ],
        )
        if not conn.entries:
            conn.unbind()
            return None

        entry = conn.entries[0]
        email = str(entry[config.attr_email]) if config.attr_email else ""
        display_name = (
            str(entry[config.attr_display_name])
            if config.attr_display_name
            else username
        )

        # Check if user exists
        user_result = await db.execute(
            select(User).where(User.username == username)
        )
        existing = user_result.scalar_one_or_none()

        if existing:
            if not existing.is_active:
                conn.unbind()
                return None
            conn.unbind()
            return existing

        # Create new user
        new_user = User(
            username=username,
            display_name=display_name,
            email=email or None,
            is_active=True,
            is_ldap=True,
        )
        db.add(new_user)
        await db.flush()

        # Assign default role
        role_result = await db.execute(
            select(Role).where(Role.code == config.default_role)
        )
        role = role_result.scalar_one_or_none()
        if role:
            db.add(UserRole(user_id=new_user.id, role_id=role.id))
            await db.flush()

        conn.unbind()
        return new_user
    except ImportError:
        log.error("ldap3 not installed")
        return None
    except Exception as e:
        log.error("LDAP auth error: %s", e)
        return None
