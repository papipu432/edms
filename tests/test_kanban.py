import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password
from app.models.document import Document, DocumentStatus
from app.models.group import Group
from app.models.lifecycle import DocumentLifecycle, DocumentLifecycleState, LifecycleType
from app.models.user import User


async def _create_user_and_token(
    db: AsyncSession, username: str = "kanbanuser"
) -> tuple[User, str]:
    user = User(
        username=username,
        email=f"{username}@example.com",
        display_name="Kanban User",
        hashed_password=hash_password("password123"),
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    token = create_access_token(data={"sub": user.username})
    return user, token


async def _create_document_with_lifecycle(
    db: AsyncSession, state: DocumentLifecycleState, filename: str = "kanban_doc.pdf"
) -> tuple[Document, DocumentLifecycle]:
    group = Group(name="Kanban Group")
    db.add(group)
    await db.flush()
    await db.refresh(group)

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

    lifecycle = DocumentLifecycle(
        document_id=doc.id,
        lifecycle_type=LifecycleType.permanent,
        state=state,
    )
    db.add(lifecycle)
    await db.flush()
    await db.refresh(lifecycle)

    return doc, lifecycle


@pytest.mark.asyncio
async def test_kanban_board_returns_columns(
    client: AsyncClient, db_session: AsyncSession
):
    """Test kanban endpoint returns board with columns."""
    _, token = await _create_user_and_token(db_session)
    doc1, _ = await _create_document_with_lifecycle(
        db_session, DocumentLifecycleState.draft, "draft_doc.pdf"
    )
    doc2, _ = await _create_document_with_lifecycle(
        db_session, DocumentLifecycleState.in_review, "review_doc.pdf"
    )

    response = await client.get(
        "/api/kanban",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "columns" in data

    # Verify draft column has our document
    assert "draft" in data["columns"]
    draft_cards = data["columns"]["draft"]
    assert any(c["document_id"] == doc1.id for c in draft_cards)

    # Verify in_review column has our document
    assert "in_review" in data["columns"]
    review_cards = data["columns"]["in_review"]
    assert any(c["document_id"] == doc2.id for c in review_cards)


@pytest.mark.asyncio
async def test_kanban_card_structure(client: AsyncClient, db_session: AsyncSession):
    """Test kanban card has expected fields."""
    _, token = await _create_user_and_token(db_session, username="kanbanstruct")
    doc, _ = await _create_document_with_lifecycle(
        db_session, DocumentLifecycleState.approved, "approved_doc.pdf"
    )

    response = await client.get(
        "/api/kanban",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()

    assert "approved" in data["columns"]
    cards = data["columns"]["approved"]
    card = next(c for c in cards if c["document_id"] == doc.id)
    assert card["filename"] == "approved_doc.pdf"
    assert card["state"] == "approved"
    assert "updated_at" in card


@pytest.mark.asyncio
async def test_kanban_empty_board(client: AsyncClient, db_session: AsyncSession):
    """Test kanban returns empty columns when no lifecycles exist."""
    _, token = await _create_user_and_token(db_session, username="kanbanempty")

    response = await client.get(
        "/api/kanban",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "columns" in data
    assert data["columns"] == {}


@pytest.mark.asyncio
async def test_kanban_requires_auth(client: AsyncClient, db_session: AsyncSession):
    """Test kanban endpoint requires authentication."""
    response = await client.get("/api/kanban")
    assert response.status_code == 401
