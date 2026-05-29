import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.group import Group


async def _create_nested_groups(db: AsyncSession) -> tuple[Group, Group, Group]:
    """Create a 3-level nested group hierarchy: root -> mid -> leaf."""
    root = Group(name="Root Group")
    db.add(root)
    await db.flush()
    await db.refresh(root)

    mid = Group(name="Mid Group", parent_id=root.id)
    db.add(mid)
    await db.flush()
    await db.refresh(mid)

    leaf = Group(name="Leaf Group", parent_id=mid.id)
    db.add(leaf)
    await db.flush()
    await db.refresh(leaf)

    return root, mid, leaf


@pytest.mark.asyncio
async def test_breadcrumbs_nested_groups(client: AsyncClient, db_session: AsyncSession):
    """Test breadcrumbs for nested groups (3 levels deep)."""
    root, mid, leaf = await _create_nested_groups(db_session)

    response = await client.get(f"/api/groups/{leaf.id}/breadcrumbs")
    assert response.status_code == 200
    data = response.json()
    items = data["items"]

    # Should be root -> mid -> leaf (3 items)
    assert len(items) == 3
    assert items[0]["name"] == "Root Group"
    assert items[0]["id"] == root.id
    assert items[1]["name"] == "Mid Group"
    assert items[1]["id"] == mid.id
    assert items[2]["name"] == "Leaf Group"
    assert items[2]["id"] == leaf.id

    # Each item has url
    for item in items:
        assert "url" in item
        assert f"/groups/{item['id']}" in item["url"]


@pytest.mark.asyncio
async def test_breadcrumbs_root_group(client: AsyncClient, db_session: AsyncSession):
    """Test root group has single breadcrumb."""
    root = Group(name="Standalone Root")
    db_session.add(root)
    await db_session.flush()
    await db_session.refresh(root)

    response = await client.get(f"/api/groups/{root.id}/breadcrumbs")
    assert response.status_code == 200
    data = response.json()
    items = data["items"]

    assert len(items) == 1
    assert items[0]["name"] == "Standalone Root"
    assert items[0]["id"] == root.id


@pytest.mark.asyncio
async def test_breadcrumbs_mid_level(client: AsyncClient, db_session: AsyncSession):
    """Test breadcrumbs for mid-level group shows 2 items."""
    root, mid, leaf = await _create_nested_groups(db_session)

    response = await client.get(f"/api/groups/{mid.id}/breadcrumbs")
    assert response.status_code == 200
    data = response.json()
    items = data["items"]

    assert len(items) == 2
    assert items[0]["name"] == "Root Group"
    assert items[1]["name"] == "Mid Group"


@pytest.mark.asyncio
async def test_breadcrumbs_not_found(client: AsyncClient, db_session: AsyncSession):
    """Test breadcrumbs for non-existent group returns 404."""
    response = await client.get("/api/groups/99999/breadcrumbs")
    assert response.status_code == 404
