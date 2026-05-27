from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password
from app.models.document import Document, DocumentStatus
from app.models.group import Group
from app.models.lifecycle import DocumentLifecycle
from app.models.user import Role, User, UserRole


async def _create_user_with_roles(
    db: AsyncSession, roles: list[str], username: str = "testuser"
) -> tuple[User, str]:
    """Helper to create a user with specified roles and return (user, token)."""
    for role_code in roles:
        existing = await db.execute(select(Role).where(Role.code == role_code))
        if existing.scalar_one_or_none() is None:
            db.add(
                Role(
                    code=role_code,
                    name=role_code.title(),
                    description=f"{role_code} role",
                    is_system=True,
                )
            )
    await db.flush()

    user = User(
        username=username,
        email=f"{username}@example.com",
        display_name="Test User",
        hashed_password=hash_password("password123"),
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)

    for role_code in roles:
        result = await db.execute(select(Role).where(Role.code == role_code))
        role = result.scalar_one()
        user_role = UserRole(user_id=user.id, role_id=role.id)
        db.add(user_role)
    await db.flush()
    await db.refresh(user)

    token = create_access_token(data={"sub": user.username})
    return user, token


async def _create_document(db: AsyncSession) -> Document:
    """Helper to create a group and document."""
    group = Group(name="Lifecycle Test Group")
    db.add(group)
    await db.flush()
    await db.refresh(group)
    doc = Document(
        group_id=group.id,
        original_filename="lifecycle_test.pdf",
        storage_path="/tmp/lifecycle_test.pdf",
        file_type="application/pdf",
        file_size=2048,
        status=DocumentStatus.uploaded,
    )
    db.add(doc)
    await db.flush()
    await db.refresh(doc)
    return doc


@pytest.mark.asyncio
async def test_create_lifecycle_permanent(
    client: AsyncClient, db_session: AsyncSession
):
    user, token = await _create_user_with_roles(db_session, ["admin"])
    doc = await _create_document(db_session)

    response = await client.post(
        f"/api/documents/{doc.id}/lifecycle",
        json={"lifecycle_type": "permanent"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["lifecycle_type"] == "permanent"
    assert data["state"] == "draft"
    assert data["expires_at"] is None
    assert data["review_interval_days"] is None
    assert data["document_id"] == doc.id


@pytest.mark.asyncio
async def test_create_lifecycle_expiring(
    client: AsyncClient, db_session: AsyncSession
):
    user, token = await _create_user_with_roles(db_session, ["admin"])
    doc = await _create_document(db_session)

    expires = (datetime.now(timezone.utc) + timedelta(days=60)).isoformat()
    response = await client.post(
        f"/api/documents/{doc.id}/lifecycle",
        json={"lifecycle_type": "expiring", "expires_at": expires},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["lifecycle_type"] == "expiring"
    assert data["expires_at"] is not None


@pytest.mark.asyncio
async def test_create_lifecycle_recurring(
    client: AsyncClient, db_session: AsyncSession
):
    user, token = await _create_user_with_roles(db_session, ["admin"])
    doc = await _create_document(db_session)

    response = await client.post(
        f"/api/documents/{doc.id}/lifecycle",
        json={"lifecycle_type": "recurring", "review_interval_days": 90},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["lifecycle_type"] == "recurring"
    assert data["review_interval_days"] == 90


@pytest.mark.asyncio
async def test_transition_draft_to_in_review(
    client: AsyncClient, db_session: AsyncSession
):
    user, token = await _create_user_with_roles(db_session, ["admin"])
    doc = await _create_document(db_session)

    await client.post(
        f"/api/documents/{doc.id}/lifecycle",
        json={"lifecycle_type": "permanent"},
        headers={"Authorization": f"Bearer {token}"},
    )

    response = await client.post(
        f"/api/documents/{doc.id}/lifecycle/transition",
        json={"target_state": "in_review", "comment": "Submitting for review"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["state"] == "in_review"


@pytest.mark.asyncio
async def test_transition_in_review_to_approved(
    client: AsyncClient, db_session: AsyncSession
):
    user, token = await _create_user_with_roles(db_session, ["admin"])
    doc = await _create_document(db_session)

    await client.post(
        f"/api/documents/{doc.id}/lifecycle",
        json={"lifecycle_type": "permanent"},
        headers={"Authorization": f"Bearer {token}"},
    )
    await client.post(
        f"/api/documents/{doc.id}/lifecycle/transition",
        json={"target_state": "in_review"},
        headers={"Authorization": f"Bearer {token}"},
    )

    response = await client.post(
        f"/api/documents/{doc.id}/lifecycle/transition",
        json={"target_state": "approved", "comment": "Approved"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["state"] == "approved"
    assert data["last_approved_at"] is not None


@pytest.mark.asyncio
async def test_transition_approved_to_up_to_date_recurring(
    client: AsyncClient, db_session: AsyncSession
):
    user, token = await _create_user_with_roles(db_session, ["admin"])
    doc = await _create_document(db_session)

    await client.post(
        f"/api/documents/{doc.id}/lifecycle",
        json={"lifecycle_type": "recurring", "review_interval_days": 90},
        headers={"Authorization": f"Bearer {token}"},
    )
    await client.post(
        f"/api/documents/{doc.id}/lifecycle/transition",
        json={"target_state": "in_review"},
        headers={"Authorization": f"Bearer {token}"},
    )
    await client.post(
        f"/api/documents/{doc.id}/lifecycle/transition",
        json={"target_state": "approved"},
        headers={"Authorization": f"Bearer {token}"},
    )

    response = await client.post(
        f"/api/documents/{doc.id}/lifecycle/transition",
        json={"target_state": "up_to_date"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["state"] == "up_to_date"
    assert data["next_review_at"] is not None


@pytest.mark.asyncio
async def test_transition_up_to_date_to_needs_re_review(
    client: AsyncClient, db_session: AsyncSession
):
    user, token = await _create_user_with_roles(db_session, ["admin"])
    doc = await _create_document(db_session)

    # Go through full cycle to up_to_date
    await client.post(
        f"/api/documents/{doc.id}/lifecycle",
        json={"lifecycle_type": "permanent"},
        headers={"Authorization": f"Bearer {token}"},
    )
    await client.post(
        f"/api/documents/{doc.id}/lifecycle/transition",
        json={"target_state": "in_review"},
        headers={"Authorization": f"Bearer {token}"},
    )
    await client.post(
        f"/api/documents/{doc.id}/lifecycle/transition",
        json={"target_state": "approved"},
        headers={"Authorization": f"Bearer {token}"},
    )
    await client.post(
        f"/api/documents/{doc.id}/lifecycle/transition",
        json={"target_state": "up_to_date"},
        headers={"Authorization": f"Bearer {token}"},
    )

    response = await client.post(
        f"/api/documents/{doc.id}/lifecycle/transition",
        json={"target_state": "needs_re_review"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["state"] == "needs_re_review"


@pytest.mark.asyncio
async def test_transition_needs_re_review_to_in_review(
    client: AsyncClient, db_session: AsyncSession
):
    user, token = await _create_user_with_roles(db_session, ["admin"])
    doc = await _create_document(db_session)

    # Go through full cycle to needs_re_review
    await client.post(
        f"/api/documents/{doc.id}/lifecycle",
        json={"lifecycle_type": "permanent"},
        headers={"Authorization": f"Bearer {token}"},
    )
    await client.post(
        f"/api/documents/{doc.id}/lifecycle/transition",
        json={"target_state": "in_review"},
        headers={"Authorization": f"Bearer {token}"},
    )
    await client.post(
        f"/api/documents/{doc.id}/lifecycle/transition",
        json={"target_state": "approved"},
        headers={"Authorization": f"Bearer {token}"},
    )
    await client.post(
        f"/api/documents/{doc.id}/lifecycle/transition",
        json={"target_state": "up_to_date"},
        headers={"Authorization": f"Bearer {token}"},
    )
    await client.post(
        f"/api/documents/{doc.id}/lifecycle/transition",
        json={"target_state": "needs_re_review"},
        headers={"Authorization": f"Bearer {token}"},
    )

    response = await client.post(
        f"/api/documents/{doc.id}/lifecycle/transition",
        json={"target_state": "in_review"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["state"] == "in_review"


@pytest.mark.asyncio
async def test_invalid_transition_rejected(
    client: AsyncClient, db_session: AsyncSession
):
    user, token = await _create_user_with_roles(db_session, ["admin"])
    doc = await _create_document(db_session)

    await client.post(
        f"/api/documents/{doc.id}/lifecycle",
        json={"lifecycle_type": "permanent"},
        headers={"Authorization": f"Bearer {token}"},
    )

    # Try draft -> approved (invalid, must go through in_review)
    response = await client.post(
        f"/api/documents/{doc.id}/lifecycle/transition",
        json={"target_state": "approved"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400
    assert "Invalid transition" in response.json()["detail"]


@pytest.mark.asyncio
async def test_transition_history(client: AsyncClient, db_session: AsyncSession):
    user, token = await _create_user_with_roles(db_session, ["admin"])
    doc = await _create_document(db_session)

    await client.post(
        f"/api/documents/{doc.id}/lifecycle",
        json={"lifecycle_type": "permanent"},
        headers={"Authorization": f"Bearer {token}"},
    )
    await client.post(
        f"/api/documents/{doc.id}/lifecycle/transition",
        json={"target_state": "in_review", "comment": "First transition"},
        headers={"Authorization": f"Bearer {token}"},
    )
    await client.post(
        f"/api/documents/{doc.id}/lifecycle/transition",
        json={"target_state": "approved", "comment": "Second transition"},
        headers={"Authorization": f"Bearer {token}"},
    )

    response = await client.get(f"/api/documents/{doc.id}/lifecycle/history")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["from_state"] == "draft"
    assert data[0]["to_state"] == "in_review"
    assert data[0]["comment"] == "First transition"
    assert data[1]["from_state"] == "in_review"
    assert data[1]["to_state"] == "approved"
    assert data[1]["comment"] == "Second transition"


@pytest.mark.asyncio
async def test_get_lifecycle_alerts_expiring(
    client: AsyncClient, db_session: AsyncSession
):
    user, token = await _create_user_with_roles(db_session, ["admin"])
    doc = await _create_document(db_session)

    expires = (datetime.now(timezone.utc) + timedelta(days=10)).isoformat()
    await client.post(
        f"/api/documents/{doc.id}/lifecycle",
        json={"lifecycle_type": "expiring", "expires_at": expires},
        headers={"Authorization": f"Bearer {token}"},
    )

    response = await client.get("/api/lifecycle/alerts?days_before_expiry=30")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    expiry_alerts = [a for a in data["alerts"] if a["alert_type"] == "expiry"]
    assert len(expiry_alerts) >= 1
    assert expiry_alerts[0]["document_id"] == doc.id
    assert expiry_alerts[0]["days_remaining"] <= 10


@pytest.mark.asyncio
async def test_get_lifecycle_alerts_needs_review(
    client: AsyncClient, db_session: AsyncSession
):
    user, token = await _create_user_with_roles(db_session, ["admin"])
    doc = await _create_document(db_session)

    # Create recurring lifecycle and advance to up_to_date with past next_review_at
    await client.post(
        f"/api/documents/{doc.id}/lifecycle",
        json={"lifecycle_type": "recurring", "review_interval_days": 1},
        headers={"Authorization": f"Bearer {token}"},
    )
    await client.post(
        f"/api/documents/{doc.id}/lifecycle/transition",
        json={"target_state": "in_review"},
        headers={"Authorization": f"Bearer {token}"},
    )
    await client.post(
        f"/api/documents/{doc.id}/lifecycle/transition",
        json={"target_state": "approved"},
        headers={"Authorization": f"Bearer {token}"},
    )
    await client.post(
        f"/api/documents/{doc.id}/lifecycle/transition",
        json={"target_state": "up_to_date"},
        headers={"Authorization": f"Bearer {token}"},
    )

    # Manually set next_review_at to the past to simulate needing review
    result = await db_session.execute(
        select(DocumentLifecycle).where(
            DocumentLifecycle.document_id == doc.id
        )
    )
    lifecycle = result.scalar_one()
    lifecycle.next_review_at = datetime.now(timezone.utc) - timedelta(days=1)
    await db_session.flush()

    response = await client.get("/api/lifecycle/alerts?days_before_review=14")
    assert response.status_code == 200
    data = response.json()
    review_alerts = [a for a in data["alerts"] if a["alert_type"] == "review"]
    assert len(review_alerts) >= 1
    assert review_alerts[0]["document_id"] == doc.id


@pytest.mark.asyncio
async def test_lifecycle_requires_auth(
    client: AsyncClient, db_session: AsyncSession
):
    doc = await _create_document(db_session)

    response = await client.post(
        f"/api/documents/{doc.id}/lifecycle",
        json={"lifecycle_type": "permanent"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_lifecycle_not_found(client: AsyncClient, db_session: AsyncSession):
    user, token = await _create_user_with_roles(db_session, ["admin"])

    response = await client.get(
        "/api/documents/9999/lifecycle",
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_check_alerts_admin_only(
    client: AsyncClient, db_session: AsyncSession
):
    user, token = await _create_user_with_roles(
        db_session, ["editor"], username="editoruser"
    )

    response = await client.post(
        "/api/lifecycle/check-alerts",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403
