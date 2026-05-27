import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_group(client: AsyncClient):
    response = await client.post(
        "/api/groups", json={"name": "Test Group", "description": "A test group"}
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Test Group"
    assert data["description"] == "A test group"
    assert "id" in data
    assert "created_at" in data


@pytest.mark.asyncio
async def test_list_groups(client: AsyncClient):
    await client.post("/api/groups", json={"name": "Group 1"})
    await client.post("/api/groups", json={"name": "Group 2"})

    response = await client.get("/api/groups")
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 2


@pytest.mark.asyncio
async def test_get_group(client: AsyncClient):
    create_response = await client.post(
        "/api/groups", json={"name": "Get Group", "description": "desc"}
    )
    group_id = create_response.json()["id"]

    response = await client.get(f"/api/groups/{group_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Get Group"
    assert data["id"] == group_id


@pytest.mark.asyncio
async def test_get_group_not_found(client: AsyncClient):
    response = await client.get("/api/groups/9999")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_group(client: AsyncClient):
    create_response = await client.post(
        "/api/groups", json={"name": "Old Name", "description": "old desc"}
    )
    group_id = create_response.json()["id"]

    response = await client.put(
        f"/api/groups/{group_id}",
        json={"name": "New Name", "description": "new desc"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "New Name"
    assert data["description"] == "new desc"


@pytest.mark.asyncio
async def test_delete_group(client: AsyncClient):
    create_response = await client.post("/api/groups", json={"name": "Delete Me"})
    group_id = create_response.json()["id"]

    response = await client.delete(f"/api/groups/{group_id}")
    assert response.status_code == 204

    get_response = await client.get(f"/api/groups/{group_id}")
    assert get_response.status_code == 404
