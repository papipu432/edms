import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.router import api_router
from app.core.config import settings
from app.core.database import engine
from app.core.security import hash_password
from app.models.group import Base
from app.models.user import (
    OrgGrade,
    OrgUnitType,
    Permission,
    Role,
    RolePermission,
    User,
    UserRole,
)

logger = logging.getLogger(__name__)

# Seed data
SYSTEM_ROLES = [
    ("admin", "Administrator", "Full system access", True),
    ("manager", "Manager", "Manage org structure and users", True),
    ("operator", "Operator", "Operate org assignments", True),
    ("viewer", "Viewer", "Read-only access", True),
    ("editor", "Editor", "Edit documents", True),
    ("reviewer", "Reviewer", "Review documents", True),
    ("annotator", "Annotator", "Annotate documents", True),
    ("approver", "Approver", "Approve workflows", True),
]

PERMISSIONS = [
    ("users", "create"),
    ("users", "read"),
    ("users", "update"),
    ("users", "delete"),
    ("roles", "create"),
    ("roles", "read"),
    ("roles", "update"),
    ("roles", "delete"),
    ("org_units", "create"),
    ("org_units", "read"),
    ("org_units", "update"),
    ("org_units", "delete"),
    ("org_positions", "create"),
    ("org_positions", "read"),
    ("org_positions", "update"),
    ("org_positions", "delete"),
    ("org_grades", "create"),
    ("org_grades", "read"),
    ("org_grades", "update"),
    ("org_grades", "delete"),
    ("org_assignments", "create"),
    ("org_assignments", "read"),
    ("org_assignments", "update"),
    ("org_assignments", "delete"),
    ("documents", "create"),
    ("documents", "read"),
    ("documents", "update"),
    ("documents", "delete"),
    ("ldap", "manage"),
    ("settings", "manage"),
    ("security", "manage"),
    ("reports", "read"),
    ("audit", "read"),
]

ROLE_PERMISSIONS = {
    "admin": "*",
    "manager": [
        "users:read",
        "users:create",
        "users:update",
        "roles:read",
        "org_units:create",
        "org_units:read",
        "org_units:update",
        "org_positions:create",
        "org_positions:read",
        "org_positions:update",
        "org_grades:read",
        "org_assignments:create",
        "org_assignments:read",
        "org_assignments:update",
        "documents:read",
        "documents:create",
        "documents:update",
        "reports:read",
        "audit:read",
    ],
    "operator": [
        "users:read",
        "org_units:read",
        "org_positions:read",
        "org_grades:read",
        "org_assignments:create",
        "org_assignments:read",
        "org_assignments:update",
        "documents:read",
        "reports:read",
    ],
    "viewer": [
        "users:read",
        "org_units:read",
        "org_positions:read",
        "org_grades:read",
        "org_assignments:read",
        "documents:read",
        "reports:read",
    ],
    "editor": [
        "documents:create",
        "documents:read",
        "documents:update",
    ],
    "reviewer": [
        "documents:read",
    ],
    "annotator": [
        "documents:read",
    ],
    "approver": [
        "documents:read",
        "documents:update",
    ],
}

UNIT_TYPES = [
    ("CORP", "Corporation", 0),
    ("DIV", "Division", 1),
    ("DEPT", "Department", 2),
    ("UNIT", "Unit", 3),
    ("TEAM", "Team", 4),
]

GRADES = [
    ("G01", "Grade 1 - Intern", 1, "Staff"),
    ("G02", "Grade 2 - Junior Staff", 2, "Staff"),
    ("G03", "Grade 3 - Staff", 3, "Staff"),
    ("G04", "Grade 4 - Senior Staff", 4, "Staff"),
    ("G05", "Grade 5 - Lead", 5, "Staff"),
    ("G06", "Grade 6 - Specialist", 6, "Supervisor"),
    ("G07", "Grade 7 - Senior Specialist", 7, "Supervisor"),
    ("G08", "Grade 8 - Supervisor", 8, "Supervisor"),
    ("G09", "Grade 9 - Senior Supervisor", 9, "Supervisor"),
    ("G10", "Grade 10 - Manager", 10, "Manager"),
    ("G11", "Grade 11 - Senior Manager", 11, "Manager"),
    ("G12", "Grade 12 - Deputy Director", 12, "Director"),
    ("G13", "Grade 13 - Director", 13, "Director"),
    ("G14", "Grade 14 - VP / General Director", 14, "Executive"),
    ("G15", "Grade 15 - C-Level / President", 15, "Executive"),
]


async def _seed_data(session: AsyncSession) -> None:
    """Create default roles, permissions, unit types, grades, and admin user."""
    # ── Permissions ───────────────────────────────────────────────────────
    perm_map: dict[str, str] = {}
    for resource, action in PERMISSIONS:
        key = f"{resource}:{action}"
        result = await session.execute(
            select(Permission).where(
                Permission.resource == resource, Permission.action == action
            )
        )
        perm = result.scalar_one_or_none()
        if perm is None:
            perm = Permission(resource=resource, action=action)
            session.add(perm)
            await session.flush()
        perm_map[key] = perm.id

    # ── Roles ─────────────────────────────────────────────────────────────
    role_map: dict[str, str] = {}
    for code, name, desc, is_system in SYSTEM_ROLES:
        result = await session.execute(select(Role).where(Role.code == code))
        role = result.scalar_one_or_none()
        if role is None:
            role = Role(code=code, name=name, description=desc, is_system=is_system)
            session.add(role)
            await session.flush()
        role_map[code] = role.id

    # ── Role-Permission mappings ──────────────────────────────────────────
    all_perm_keys = list(perm_map.keys())
    for role_code, grants in ROLE_PERMISSIONS.items():
        role_id = role_map.get(role_code)
        if not role_id:
            continue
        keys_to_grant = all_perm_keys if grants == "*" else grants
        for key in keys_to_grant:
            perm_id = perm_map.get(key)
            if not perm_id:
                continue
            result = await session.execute(
                select(RolePermission).where(
                    RolePermission.role_id == role_id,
                    RolePermission.permission_id == perm_id,
                )
            )
            if result.scalar_one_or_none() is None:
                session.add(RolePermission(role_id=role_id, permission_id=perm_id))

    # ── Unit Types ────────────────────────────────────────────────────────
    for code, name, order in UNIT_TYPES:
        result = await session.execute(
            select(OrgUnitType).where(OrgUnitType.code == code)
        )
        if result.scalar_one_or_none() is None:
            session.add(OrgUnitType(code=code, name=name, sort_order=order))

    # ── Grades ────────────────────────────────────────────────────────────
    for code, name, level, cat in GRADES:
        result = await session.execute(
            select(OrgGrade).where(OrgGrade.grade_code == code)
        )
        if result.scalar_one_or_none() is None:
            session.add(
                OrgGrade(
                    grade_code=code,
                    grade_name=name,
                    grade_level=level,
                    grade_category=cat,
                )
            )

    # ── Bootstrap Admin ───────────────────────────────────────────────────
    result = await session.execute(
        select(User).where(User.username == settings.BOOTSTRAP_ADMIN_USERNAME)
    )
    admin_user = result.scalar_one_or_none()
    if admin_user is None:
        admin_user = User(
            username=settings.BOOTSTRAP_ADMIN_USERNAME,
            display_name="System Administrator",
            email=settings.BOOTSTRAP_ADMIN_EMAIL,
            hashed_password=hash_password(settings.BOOTSTRAP_ADMIN_PASSWORD),
        )
        session.add(admin_user)
        await session.flush()

        admin_role_id = role_map.get("admin")
        if admin_role_id:
            session.add(UserRole(user_id=admin_user.id, role_id=admin_role_id))

    await session.commit()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    if settings.PDF_ENCRYPTION_PASSWORD == "changeme":
        logger.warning(
            "PDF_ENCRYPTION_PASSWORD is set to the default 'changeme'. "
            "This is insecure for production deployments. "
            "Set a strong password via the PDF_ENCRYPTION_PASSWORD environment variable."
        )
    if settings.SECRET_KEY == "changeme-secret-key-for-jwt":
        logger.warning(
            "SECRET_KEY is set to the default 'changeme-secret-key-for-jwt'. "
            "This is insecure for production deployments. "
            "Set a strong secret via the SECRET_KEY environment variable."
        )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Seed roles, permissions, and default admin
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        await _seed_data(session)

    yield


app = FastAPI(title="EDMS", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)
