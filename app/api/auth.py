from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security import (
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)
from app.models.user import User
from app.schemas.user import LoginRequest, Token, UserCreate, UserResponse

router = APIRouter(tags=["auth"])
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


# ── API Endpoints (Bearer token) ──────────────────────────────────────────────


@router.post(
    "/api/auth/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED
)
async def register(user_data: UserCreate, db: AsyncSession = Depends(get_db)):
    if not settings.ALLOW_REGISTRATION:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Registration is disabled",
        )

    # Check if username or email already exists
    result = await db.execute(
        select(User).where(
            (User.username == user_data.username) | (User.email == user_data.email)
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username or email already registered",
        )

    user = User(
        username=user_data.username,
        email=user_data.email,
        display_name=user_data.username,
        hashed_password=hash_password(user_data.password),
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)

    return UserResponse(
        id=user.id,
        username=user.username,
        email=user.email or "",
        is_active=user.is_active,
        roles=user.role_codes,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


@router.post("/api/auth/login", response_model=Token)
async def login(login_data: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(User).where(User.username == login_data.username)
    )
    user = result.scalar_one_or_none()
    if user is None or not user.hashed_password or not verify_password(
        login_data.password, user.hashed_password
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User is inactive",
        )

    access_token = create_access_token(data={"sub": user.username})
    return Token(access_token=access_token)


@router.get("/api/auth/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    return UserResponse(
        id=current_user.id,
        username=current_user.username,
        email=current_user.email or "",
        is_active=current_user.is_active,
        roles=current_user.role_codes,
        created_at=current_user.created_at,
        updated_at=current_user.updated_at,
    )


# ── Session Cookie Endpoints (HTML form) ──────────────────────────────────────


@router.post("/auth/login")
async def html_login(request: Request, db: AsyncSession = Depends(get_db)):
    """HTML form login - sets session cookie."""
    form = await request.form()
    username = form.get("username", "")
    password = form.get("password", "")

    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if user is None or not user.hashed_password or not verify_password(
        str(password), user.hashed_password
    ):
        return templates.TemplateResponse(
            request, "login.html", {"error": "Invalid credentials"}, status_code=401
        )
    if not user.is_active:
        return templates.TemplateResponse(
            request, "login.html", {"error": "User is inactive"}, status_code=401
        )

    access_token = create_access_token(data={"sub": user.username})
    response = RedirectResponse(url="/dashboard", status_code=303)
    is_secure = request.url.scheme == "https"
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        samesite="lax",
        secure=is_secure,
    )
    return response


@router.get("/auth/logout")
async def html_logout():
    """Clear session cookie and redirect to login."""
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(key="access_token")
    return response


@router.get("/auth/profile")
async def profile_page(request: Request, user: User = Depends(get_current_user)):
    return templates.TemplateResponse(
        request,
        "auth/profile.html",
        {
            "user": user,
            "roles": user.role_codes,
            "permissions": user.permissions,
        },
    )
