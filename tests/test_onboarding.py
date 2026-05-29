import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password
from app.models.user import User


async def _create_user_and_token(
    db: AsyncSession, username: str = "onboarduser"
) -> tuple[User, str]:
    user = User(
        username=username,
        email=f"{username}@example.com",
        display_name="Onboarding User",
        hashed_password=hash_password("password123"),
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    token = create_access_token(data={"sub": user.username})
    return user, token


@pytest.mark.asyncio
async def test_onboarding_status_initially_false(
    client: AsyncClient, db_session: AsyncSession
):
    """Test GET onboarding status returns completed=False initially."""
    _, token = await _create_user_and_token(db_session)

    response = await client.get(
        "/api/onboarding/status",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["completed"] is False


@pytest.mark.asyncio
async def test_complete_onboarding(client: AsyncClient, db_session: AsyncSession):
    """Test POST complete sets onboarding to True."""
    _, token = await _create_user_and_token(db_session, username="onboardcomplete")

    response = await client.post(
        "/api/onboarding/complete",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["completed"] is True


@pytest.mark.asyncio
async def test_onboarding_status_after_complete(
    client: AsyncClient, db_session: AsyncSession
):
    """Test GET status returns True after completing onboarding."""
    _, token = await _create_user_and_token(db_session, username="onboardafter")

    # Complete onboarding
    await client.post(
        "/api/onboarding/complete",
        headers={"Authorization": f"Bearer {token}"},
    )

    # Check status
    response = await client.get(
        "/api/onboarding/status",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["completed"] is True


@pytest.mark.asyncio
async def test_onboarding_requires_auth(client: AsyncClient, db_session: AsyncSession):
    """Test onboarding endpoints require authentication."""
    response = await client.get("/api/onboarding/status")
    assert response.status_code == 401

    response = await client.post("/api/onboarding/complete")
    assert response.status_code == 401
