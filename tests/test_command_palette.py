import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password
from app.models.document import Document, DocumentStatus
from app.models.group import Group
from app.models.user import User


async def _create_user_and_token(
    db: AsyncSession, username: str = "cpuser"
) -> tuple[User, str]:
    user = User(
        username=username,
        email=f"{username}@example.com",
        display_name="Command Palette User",
        hashed_password=hash_password("password123"),
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    token = create_access_token(data={"sub": user.username})
    return user, token


async def _create_group_and_documents(db: AsyncSession) -> tuple[Group, list[Document]]:
    group = Group(name="Search Group")
    db.add(group)
    await db.flush()
    await db.refresh(group)

    docs = []
    for name in ["quarterly_report.pdf", "annual_report.pdf", "meeting_notes.txt"]:
        doc = Document(
            group_id=group.id,
            original_filename=name,
            storage_path=f"/tmp/{name}",
            file_type="application/pdf",
            file_size=1024,
            status=DocumentStatus.uploaded,
        )
        db.add(doc)
        docs.append(doc)

    await db.flush()
    for doc in docs:
        await db.refresh(doc)
    return group, docs


@pytest.mark.asyncio
async def test_search_finds_documents(client: AsyncClient, db_session: AsyncSession):
    """Test command palette search returns matching documents."""
    _, token = await _create_user_and_token(db_session)
    group, docs = await _create_group_and_documents(db_session)

    response = await client.get(
        "/api/command-palette/search?q=report",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    results = data["results"]
    # Should find the two report documents
    doc_results = [r for r in results if r["type"] == "document"]
    assert len(doc_results) >= 2
    titles = [r["title"] for r in doc_results]
    assert "quarterly_report.pdf" in titles
    assert "annual_report.pdf" in titles


@pytest.mark.asyncio
async def test_search_finds_groups(client: AsyncClient, db_session: AsyncSession):
    """Test command palette search returns matching groups."""
    _, token = await _create_user_and_token(db_session, username="cpgrp")
    group, _ = await _create_group_and_documents(db_session)

    response = await client.get(
        "/api/command-palette/search?q=Search",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    group_results = [r for r in data["results"] if r["type"] == "group"]
    assert len(group_results) >= 1
    assert any(r["title"] == "Search Group" for r in group_results)


@pytest.mark.asyncio
async def test_search_empty_results(client: AsyncClient, db_session: AsyncSession):
    """Test command palette search returns empty for no match."""
    _, token = await _create_user_and_token(db_session, username="cpempty")

    response = await client.get(
        "/api/command-palette/search?q=xyznonexistent123",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["results"] == []


@pytest.mark.asyncio
async def test_search_empty_query(client: AsyncClient, db_session: AsyncSession):
    """Test command palette search with empty query returns empty results."""
    _, token = await _create_user_and_token(db_session, username="cpblank")

    response = await client.get(
        "/api/command-palette/search?q=",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["results"] == []


@pytest.mark.asyncio
async def test_search_requires_auth(client: AsyncClient, db_session: AsyncSession):
    """Test command palette search requires authentication."""
    response = await client.get("/api/command-palette/search?q=test")
    assert response.status_code == 401
