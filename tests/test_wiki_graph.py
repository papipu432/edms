"""Tests for the Wiki Graph feature."""

from pathlib import Path
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient


@pytest_asyncio.fixture
async def graph_client(tmp_path: Path) -> AsyncClient:
    """Create a test client with wiki path and auth configured."""
    from app.core.security import get_current_user
    from app.main import app
    from app.models.user import User

    # Create a wiki with linked pages
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    (wiki / "entities").mkdir()
    (wiki / "topics").mkdir()
    (wiki / "summaries").mkdir()

    (wiki / "entities" / "acme-corp.md").write_text(
        "# Acme Corp\n\nReferenced in [Report](../summaries/1.md).\n",
        encoding="utf-8",
    )
    (wiki / "topics" / "finance.md").write_text(
        "# Finance\n\nSee [Acme](../entities/acme-corp.md).\n",
        encoding="utf-8",
    )
    (wiki / "summaries" / "1.md").write_text(
        "# Report\n\nAbout [Finance](../topics/finance.md).\n",
        encoding="utf-8",
    )

    mock_user = User(
        id="test-graph-user",
        username="graph_tester",
        display_name="Graph Tester",
        email="graph@test.com",
        hashed_password="fakehash",
        is_active=True,
    )

    async def override_get_current_user() -> User:
        return mock_user

    app.dependency_overrides[get_current_user] = override_get_current_user

    with patch("app.api.wiki_graph.settings") as mock_settings:
        mock_settings.WIKI_PATH = str(wiki)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac

    app.dependency_overrides.clear()


class TestWikiGraphData:
    """Tests for the wiki graph data endpoint."""

    @pytest.mark.anyio
    async def test_graph_data_returns_nodes_and_edges(self, graph_client: AsyncClient):
        """GET /api/wiki/graph/data should return nodes and edges."""
        response = await graph_client.get("/api/wiki/graph/data")

        assert response.status_code == 200
        data = response.json()
        assert "nodes" in data
        assert "edges" in data
        assert len(data["nodes"]) == 3
        assert len(data["edges"]) >= 1

    @pytest.mark.anyio
    async def test_graph_nodes_have_required_fields(self, graph_client: AsyncClient):
        """Each node should have id, label, type, color, path."""
        response = await graph_client.get("/api/wiki/graph/data")
        data = response.json()

        for node in data["nodes"]:
            assert "id" in node
            assert "label" in node
            assert "type" in node
            assert "color" in node
            assert "path" in node

    @pytest.mark.anyio
    async def test_graph_nodes_color_coded(self, graph_client: AsyncClient):
        """Nodes should be color-coded by type."""
        response = await graph_client.get("/api/wiki/graph/data")
        data = response.json()

        color_map = {
            "entity": "#3b82f6",
            "topic": "#10b981",
            "summary": "#f59e0b",
        }
        for node in data["nodes"]:
            expected_color = color_map.get(node["type"])
            if expected_color:
                assert node["color"] == expected_color

    @pytest.mark.anyio
    async def test_graph_edges_have_source_and_target(self, graph_client: AsyncClient):
        """Each edge should have source and target."""
        response = await graph_client.get("/api/wiki/graph/data")
        data = response.json()

        for edge in data["edges"]:
            assert "source" in edge
            assert "target" in edge


class TestWikiGraphPage:
    """Tests for the wiki graph HTML page."""

    @pytest.mark.anyio
    async def test_graph_page_renders(self, graph_client: AsyncClient):
        """GET /pages/wiki/graph should return HTML."""
        response = await graph_client.get("/pages/wiki/graph")

        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")
        assert "Wiki Graph" in response.text
        assert "vis-network" in response.text
