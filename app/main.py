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
from app.models.user import Role, RoleName, User

logger = logging.getLogger(__name__)


async def _seed_roles_and_admin(session: AsyncSession) -> None:
    """Create default roles and admin user if they do not exist."""
    # Create all roles if missing
    for role_name in RoleName:
        result = await session.execute(select(Role).where(Role.name == role_name))
        if result.scalar_one_or_none() is None:
            session.add(Role(name=role_name, description=f"{role_name.value} role"))

    await session.flush()

    # Create default admin user if no users exist
    result = await session.execute(select(User))
    if result.first() is None:
        admin_role_result = await session.execute(
            select(Role).where(Role.name == RoleName.admin)
        )
        admin_role = admin_role_result.scalar_one()

        admin_user = User(
            username="admin",
            email="admin@edms.local",
            hashed_password=hash_password("admin"),
        )
        admin_user.roles.append(admin_role)
        session.add(admin_user)

    await session.commit()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    if settings.PDF_ENCRYPTION_PASSWORD == "changeme":
        logger.warning(
            "PDF_ENCRYPTION_PASSWORD is set to the default 'changeme'. "
            "This is insecure for production deployments. "
            "Set a strong password via the PDF_ENCRYPTION_PASSWORD environment variable."
        )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Seed roles and default admin
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        await _seed_roles_and_admin(session)

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
