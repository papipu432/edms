"""Tests for the Canvas/Whiteboard feature."""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.core.database import get_db
from app.main import app
from app.models.user import User


@pytest_asyncio.fixture
async def canvas_client(db_session: AsyncSession) -> AsyncClient:
    """Create a test client with auth and DB configured."""
    mock_user = User(
        id="test-canvas-user",
        username="canvas_tester",
        display_name="Canvas Tester",
        email="canvas@test.com",
        hashed_password="fakehash",
        is_active=True,
    )

    async def override_get_current_user() -> User:
        return mock_user

    async def override_get_db():
        try:
            yield db_session
            await db_session.commit()
        except Exception:
            await db_session.rollback()
            raise

    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


class TestCanvasCRUD:
    """Tests for canvas CRUD operations."""

    @pytest.mark.anyio
    async def test_create_canvas(self, canvas_client: AsyncClient):
        response = await canvas_client.post(
            "/api/canvas", json={"name": "My Canvas"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "My Canvas"
        assert data["owner_id"] == "test-canvas-user"
        assert "id" in data

    @pytest.mark.anyio
    async def test_list_canvases(self, canvas_client: AsyncClient):
        await canvas_client.post("/api/canvas", json={"name": "Canvas 1"})
        await canvas_client.post("/api/canvas", json={"name": "Canvas 2"})

        response = await canvas_client.get("/api/canvas")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

    @pytest.mark.anyio
    async def test_get_canvas(self, canvas_client: AsyncClient):
        create_resp = await canvas_client.post(
            "/api/canvas", json={"name": "Test Canvas"}
        )
        canvas_id = create_resp.json()["id"]

        response = await canvas_client.get(f"/api/canvas/{canvas_id}")
        assert response.status_code == 200
        assert response.json()["name"] == "Test Canvas"

    @pytest.mark.anyio
    async def test_update_canvas(self, canvas_client: AsyncClient):
        create_resp = await canvas_client.post(
            "/api/canvas", json={"name": "Original"}
        )
        canvas_id = create_resp.json()["id"]

        response = await canvas_client.put(
            f"/api/canvas/{canvas_id}", json={"name": "Updated"}
        )
        assert response.status_code == 200
        assert response.json()["name"] == "Updated"

    @pytest.mark.anyio
    async def test_delete_canvas(self, canvas_client: AsyncClient):
        create_resp = await canvas_client.post(
            "/api/canvas", json={"name": "To Delete"}
        )
        canvas_id = create_resp.json()["id"]

        response = await canvas_client.delete(f"/api/canvas/{canvas_id}")
        assert response.status_code == 200

        get_resp = await canvas_client.get(f"/api/canvas/{canvas_id}")
        assert get_resp.status_code == 404

    @pytest.mark.anyio
    async def test_get_nonexistent_canvas(self, canvas_client: AsyncClient):
        response = await canvas_client.get("/api/canvas/99999")
        assert response.status_code == 404


class TestCanvasItemCRUD:
    """Tests for canvas item CRUD operations."""

    @pytest.mark.anyio
    async def test_create_item(self, canvas_client: AsyncClient):
        create_resp = await canvas_client.post(
            "/api/canvas", json={"name": "Item Canvas"}
        )
        canvas_id = create_resp.json()["id"]

        response = await canvas_client.post(
            f"/api/canvas/{canvas_id}/items",
            json={
                "note_text": "Hello World",
                "x_position": 100.0,
                "y_position": 200.0,
                "width": 150.0,
                "height": 75.0,
                "color": "#ff0000",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["note_text"] == "Hello World"
        assert data["x_position"] == 100.0
        assert data["y_position"] == 200.0
        assert data["color"] == "#ff0000"

    @pytest.mark.anyio
    async def test_list_items(self, canvas_client: AsyncClient):
        create_resp = await canvas_client.post(
            "/api/canvas", json={"name": "Items Canvas"}
        )
        canvas_id = create_resp.json()["id"]

        await canvas_client.post(
            f"/api/canvas/{canvas_id}/items",
            json={"note_text": "Item 1", "x_position": 0, "y_position": 0},
        )
        await canvas_client.post(
            f"/api/canvas/{canvas_id}/items",
            json={"note_text": "Item 2", "x_position": 100, "y_position": 100},
        )

        response = await canvas_client.get(f"/api/canvas/{canvas_id}/items")
        assert response.status_code == 200
        assert len(response.json()) == 2

    @pytest.mark.anyio
    async def test_update_item(self, canvas_client: AsyncClient):
        create_resp = await canvas_client.post(
            "/api/canvas", json={"name": "Update Canvas"}
        )
        canvas_id = create_resp.json()["id"]

        item_resp = await canvas_client.post(
            f"/api/canvas/{canvas_id}/items",
            json={"note_text": "Original", "x_position": 0, "y_position": 0},
        )
        item_id = item_resp.json()["id"]

        response = await canvas_client.put(
            f"/api/canvas/{canvas_id}/items/{item_id}",
            json={"x_position": 300.0, "y_position": 400.0},
        )
        assert response.status_code == 200
        assert response.json()["x_position"] == 300.0
        assert response.json()["y_position"] == 400.0

    @pytest.mark.anyio
    async def test_delete_item(self, canvas_client: AsyncClient):
        create_resp = await canvas_client.post(
            "/api/canvas", json={"name": "Delete Item Canvas"}
        )
        canvas_id = create_resp.json()["id"]

        item_resp = await canvas_client.post(
            f"/api/canvas/{canvas_id}/items",
            json={"note_text": "Delete me", "x_position": 0, "y_position": 0},
        )
        item_id = item_resp.json()["id"]

        response = await canvas_client.delete(
            f"/api/canvas/{canvas_id}/items/{item_id}"
        )
        assert response.status_code == 200

        list_resp = await canvas_client.get(f"/api/canvas/{canvas_id}/items")
        assert len(list_resp.json()) == 0


class TestCanvasConnectionCRUD:
    """Tests for canvas connection CRUD operations."""

    @pytest.mark.anyio
    async def test_create_connection(self, canvas_client: AsyncClient):
        create_resp = await canvas_client.post(
            "/api/canvas", json={"name": "Conn Canvas"}
        )
        canvas_id = create_resp.json()["id"]

        item1 = await canvas_client.post(
            f"/api/canvas/{canvas_id}/items",
            json={"note_text": "A", "x_position": 0, "y_position": 0},
        )
        item2 = await canvas_client.post(
            f"/api/canvas/{canvas_id}/items",
            json={"note_text": "B", "x_position": 200, "y_position": 0},
        )
        item1_id = item1.json()["id"]
        item2_id = item2.json()["id"]

        response = await canvas_client.post(
            f"/api/canvas/{canvas_id}/connections",
            json={
                "from_item_id": item1_id,
                "to_item_id": item2_id,
                "label": "relates to",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["from_item_id"] == item1_id
        assert data["to_item_id"] == item2_id
        assert data["label"] == "relates to"

    @pytest.mark.anyio
    async def test_list_connections(self, canvas_client: AsyncClient):
        create_resp = await canvas_client.post(
            "/api/canvas", json={"name": "List Conn Canvas"}
        )
        canvas_id = create_resp.json()["id"]

        item1 = await canvas_client.post(
            f"/api/canvas/{canvas_id}/items",
            json={"note_text": "X", "x_position": 0, "y_position": 0},
        )
        item2 = await canvas_client.post(
            f"/api/canvas/{canvas_id}/items",
            json={"note_text": "Y", "x_position": 200, "y_position": 0},
        )
        item1_id = item1.json()["id"]
        item2_id = item2.json()["id"]

        await canvas_client.post(
            f"/api/canvas/{canvas_id}/connections",
            json={"from_item_id": item1_id, "to_item_id": item2_id},
        )

        response = await canvas_client.get(
            f"/api/canvas/{canvas_id}/connections"
        )
        assert response.status_code == 200
        assert len(response.json()) == 1

    @pytest.mark.anyio
    async def test_delete_connection(self, canvas_client: AsyncClient):
        create_resp = await canvas_client.post(
            "/api/canvas", json={"name": "Del Conn Canvas"}
        )
        canvas_id = create_resp.json()["id"]

        item1 = await canvas_client.post(
            f"/api/canvas/{canvas_id}/items",
            json={"note_text": "P", "x_position": 0, "y_position": 0},
        )
        item2 = await canvas_client.post(
            f"/api/canvas/{canvas_id}/items",
            json={"note_text": "Q", "x_position": 200, "y_position": 0},
        )
        item1_id = item1.json()["id"]
        item2_id = item2.json()["id"]

        conn_resp = await canvas_client.post(
            f"/api/canvas/{canvas_id}/connections",
            json={"from_item_id": item1_id, "to_item_id": item2_id},
        )
        conn_id = conn_resp.json()["id"]

        response = await canvas_client.delete(
            f"/api/canvas/{canvas_id}/connections/{conn_id}"
        )
        assert response.status_code == 200

        list_resp = await canvas_client.get(
            f"/api/canvas/{canvas_id}/connections"
        )
        assert len(list_resp.json()) == 0


class TestCanvasExport:
    """Tests for canvas export as Obsidian .canvas format."""

    @pytest.mark.anyio
    async def test_export_canvas_format(self, canvas_client: AsyncClient):
        """GET /api/canvas/{id}/export should return Obsidian .canvas JSON."""
        create_resp = await canvas_client.post(
            "/api/canvas", json={"name": "Export Canvas"}
        )
        canvas_id = create_resp.json()["id"]

        item1 = await canvas_client.post(
            f"/api/canvas/{canvas_id}/items",
            json={"note_text": "Node A", "x_position": 10, "y_position": 20, "width": 200, "height": 100},
        )
        item2 = await canvas_client.post(
            f"/api/canvas/{canvas_id}/items",
            json={"note_text": "Node B", "x_position": 300, "y_position": 20, "width": 200, "height": 100},
        )
        item1_id = item1.json()["id"]
        item2_id = item2.json()["id"]

        await canvas_client.post(
            f"/api/canvas/{canvas_id}/connections",
            json={"from_item_id": item1_id, "to_item_id": item2_id, "label": "link"},
        )

        response = await canvas_client.get(f"/api/canvas/{canvas_id}/export")
        assert response.status_code == 200
        data = response.json()

        assert "nodes" in data
        assert "edges" in data
        assert len(data["nodes"]) == 2
        assert len(data["edges"]) == 1

        # Check node structure
        node = data["nodes"][0]
        assert "id" in node
        assert "x" in node
        assert "y" in node
        assert "width" in node
        assert "height" in node
        assert "type" in node

        # Check edge structure
        edge = data["edges"][0]
        assert "id" in edge
        assert "fromNode" in edge
        assert "toNode" in edge
        assert edge["label"] == "link"

    @pytest.mark.anyio
    async def test_export_nonexistent_canvas(self, canvas_client: AsyncClient):
        response = await canvas_client.get("/api/canvas/99999/export")
        assert response.status_code == 404
