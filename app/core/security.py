from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.models.user import User

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security_scheme = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def _decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        return None


async def _get_user_from_token(token: str, db: AsyncSession) -> User | None:
    """Resolve a JWT token to a User object."""
    payload = _decode_token(token)
    if payload is None:
        return None
    username: str | None = payload.get("sub")
    if username is None:
        return None
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        return None
    return user


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Get current user from Bearer token (API) or session cookie (HTML)."""
    token: str | None = None

    # Try Bearer token first
    if credentials is not None:
        token = credentials.credentials
    else:
        # Fall back to session cookie
        token = request.cookies.get("access_token")

    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated"
        )

    user = await _get_user_from_token(token, db)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid token")
    return user


async def get_optional_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security_scheme),
    db: AsyncSession = Depends(get_db),
) -> User | None:
    """Get current user if token provided, otherwise return None."""
    token: str | None = None
    if credentials is not None:
        token = credentials.credentials
    else:
        token = request.cookies.get("access_token")

    if token is None:
        return None
    return await _get_user_from_token(token, db)


def role_required(required_roles: list[str]):
    """Dependency factory that checks if user has any of the required roles."""

    async def check_role(current_user: User = Depends(get_current_user)) -> User:
        user_roles = current_user.role_codes
        if "admin" in user_roles:
            return current_user
        if not any(role in user_roles for role in required_roles):
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return current_user

    return check_role


def require_auth():
    """Dependency that requires authentication (any valid user)."""

    async def _check(current_user: User = Depends(get_current_user)) -> User:
        return current_user

    return _check


def require_role(*roles: str):
    """Dependency factory - user must have at least one of the given roles."""

    async def _check(current_user: User = Depends(get_current_user)) -> User:
        user_roles = set(current_user.role_codes)
        if "admin" in user_roles:
            return current_user
        if not user_roles.intersection(roles):
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return current_user

    return _check


def require_permission(resource: str, action: str):
    """Dependency factory - user must have resource:action permission."""

    async def _check(current_user: User = Depends(get_current_user)) -> User:
        user_roles = set(current_user.role_codes)
        if "admin" in user_roles:
            return current_user
        needed = f"{resource}:{action}"
        if needed not in current_user.permissions:
            raise HTTPException(
                status_code=403, detail=f"Missing permission: {needed}"
            )
        return current_user

    return _check
