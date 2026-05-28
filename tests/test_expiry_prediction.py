import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password
from app.models.document import Document, DocumentStatus
from app.models.group import Group
from app.models.lifecycle import DocumentLifecycle, DocumentLifecycleState, LifecycleType
from app.models.user import User


async def _create_user_and_token(
    db: AsyncSession, username: str = "expiryuser"
) -> tuple[User, str]:
    user = User(
        username=username,
        email=f"{username}@example.com",
        display_name="Expiry User",
        hashed_password=hash_password("password123"),
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    token = create_access_token(data={"sub": user.username})
    return user, token


async def _create_document(
    db: AsyncSession, group: Group, filename: str = "expiry_doc.pdf"
) -> Document:
    doc = Document(
        group_id=group.id,
        original_filename=filename,
        storage_path=f"/tmp/{filename}",
        file_type="application/pdf",
        file_size=1024,
        status=DocumentStatus.uploaded,
    )
    db.add(doc)
    await db.flush()
    await db.refresh(doc)
    return doc


@pytest.mark.asyncio
async def test_expiry_prediction_with_lifecycle(
    client: AsyncClient, db_session: AsyncSession
):
    """Test prediction endpoint returns prediction data for document with lifecycle."""
    _, token = await _create_user_and_token(db_session)

    group = Group(name="Expiry Group")
    db_session.add(group)
    await db_session.flush()
    await db_session.refresh(group)

    doc = await _create_document(db_session, group)

    # Create lifecycle with review_interval_days
    lifecycle = DocumentLifecycle(
        document_id=doc.id,
        lifecycle_type=LifecycleType.recurring,
        state=DocumentLifecycleState.up_to_date,
        review_interval_days=30,
    )
    db_session.add(lifecycle)
    await db_session.flush()

    response = await client.get(
        f"/api/documents/{doc.id}/expiry-prediction",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["document_id"] == doc.id
    assert "predicted_review_date" in data
    assert "confidence" in data
    assert "based_on_count" in data
    assert data["based_on_count"] >= 1
    assert data["confidence"] > 0.0


@pytest.mark.asyncio
async def test_expiry_prediction_no_lifecycle(
    client: AsyncClient, db_session: AsyncSession
):
    """Test prediction endpoint handles document without lifecycle gracefully."""
    _, token = await _create_user_and_token(db_session, username="expnolc")

    group = Group(name="No Lifecycle Group")
    db_session.add(group)
    await db_session.flush()
    await db_session.refresh(group)

    doc = await _create_document(db_session, group, "no_lifecycle.pdf")

    response = await client.get(
        f"/api/documents/{doc.id}/expiry-prediction",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404
    assert "lifecycle" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_expiry_prediction_no_review_data(
    client: AsyncClient, db_session: AsyncSession
):
    """Test prediction with no review interval data returns zero confidence."""
    _, token = await _create_user_and_token(db_session, username="expnodata")

    group = Group(name="No Data Group")
    db_session.add(group)
    await db_session.flush()
    await db_session.refresh(group)

    doc = await _create_document(db_session, group, "no_data.pdf")

    # Create lifecycle without review_interval_days
    lifecycle = DocumentLifecycle(
        document_id=doc.id,
        lifecycle_type=LifecycleType.permanent,
        state=DocumentLifecycleState.draft,
    )
    db_session.add(lifecycle)
    await db_session.flush()

    response = await client.get(
        f"/api/documents/{doc.id}/expiry-prediction",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["document_id"] == doc.id
    assert data["confidence"] == 0.0
    assert data["based_on_count"] == 0


@pytest.mark.asyncio
async def test_expiry_prediction_document_not_found(
    client: AsyncClient, db_session: AsyncSession
):
    """Test prediction for non-existent document returns 404."""
    _, token = await _create_user_and_token(db_session, username="expnf")

    response = await client.get(
        "/api/documents/99999/expiry-prediction",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_expiry_prediction_requires_auth(
    client: AsyncClient, db_session: AsyncSession
):
    """Test expiry prediction requires authentication."""
    response = await client.get("/api/documents/1/expiry-prediction")
    assert response.status_code == 401
