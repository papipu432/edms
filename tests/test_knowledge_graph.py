import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select

from app.core.security import create_access_token, hash_password
from app.models.document import Document, DocumentStatus
from app.models.group import Group
from app.models.relationship import DocumentRelationship, RelationshipType
from app.models.user import Role, User, UserRole
from app.services.knowledge_graph import KnowledgeGraphService


@pytest_asyncio.fixture
async def seeded_db(db_session):
    """Seed roles into the test database."""
    roles_data = [
        ("admin", "Administrator"),
        ("editor", "Editor"),
    ]
    for code, name in roles_data:
        db_session.add(Role(code=code, name=name, description=f"{code} role", is_system=True))
    await db_session.flush()
    return db_session


@pytest_asyncio.fixture
async def test_user(seeded_db):
    """Create a test user."""
    result = await seeded_db.execute(select(Role).where(Role.code == "admin"))
    admin_role = result.scalar_one()

    user = User(
        username="graphuser",
        email="graph@edms.local",
        display_name="Graph User",
        hashed_password=hash_password("password"),
    )
    seeded_db.add(user)
    await seeded_db.flush()
    await seeded_db.refresh(user)

    user_role = UserRole(user_id=user.id, role_id=admin_role.id)
    seeded_db.add(user_role)
    await seeded_db.flush()
    await seeded_db.refresh(user)
    return user


@pytest_asyncio.fixture
async def auth_token(test_user):
    """Create a valid JWT token for the test user."""
    return create_access_token(data={"sub": test_user.username})


@pytest_asyncio.fixture
async def test_group(seeded_db):
    """Create a test group."""
    group = Group(name="Graph Test Group", description="For graph tests")
    seeded_db.add(group)
    await seeded_db.flush()
    await seeded_db.refresh(group)
    return group


@pytest_asyncio.fixture
async def test_documents_with_relationships(seeded_db, test_group, test_user, tmp_path):
    """Create test documents with relationships."""
    doc_a = Document(
        group_id=test_group.id,
        original_filename="report.pdf",
        storage_path=str(tmp_path / "report.pdf"),
        file_type="application/pdf",
        file_size=1024,
        status=DocumentStatus.processed,
        keywords=["finance", "quarterly"],
    )
    seeded_db.add(doc_a)
    await seeded_db.flush()
    await seeded_db.refresh(doc_a)

    doc_b = Document(
        group_id=test_group.id,
        original_filename="appendix.pdf",
        storage_path=str(tmp_path / "appendix.pdf"),
        file_type="application/pdf",
        file_size=512,
        status=DocumentStatus.processed,
        keywords=["finance", "data"],
    )
    seeded_db.add(doc_b)
    await seeded_db.flush()
    await seeded_db.refresh(doc_b)

    # Create a relationship
    rel = DocumentRelationship(
        source_document_id=doc_a.id,
        target_document_id=doc_b.id,
        relationship_type=RelationshipType.references,
        description="Report references appendix",
        created_by=test_user.id,
    )
    seeded_db.add(rel)
    await seeded_db.flush()

    return doc_a, doc_b


@pytest.mark.asyncio
class TestKnowledgeGraphService:
    """Unit tests for KnowledgeGraphService."""

    async def test_build_graph_returns_nodes_and_edges(
        self, db_session, test_documents_with_relationships
    ):
        """Test that graph building returns proper nodes and edges."""
        service = KnowledgeGraphService()
        result = await service.build_graph(db=db_session)

        assert len(result.nodes) > 0
        assert len(result.edges) > 0

        # Check for document nodes
        doc_nodes = [n for n in result.nodes if n.type == "document"]
        assert len(doc_nodes) == 2

        # Check for group node
        group_nodes = [n for n in result.nodes if n.type == "group"]
        assert len(group_nodes) == 1

        # Check for entity nodes from keywords
        entity_nodes = [n for n in result.nodes if n.type == "entity"]
        assert len(entity_nodes) >= 2  # "finance", "quarterly", "data"

    async def test_build_graph_with_document_filter(
        self, db_session, test_documents_with_relationships
    ):
        """Test graph filtering by document_id."""
        doc_a, _ = test_documents_with_relationships
        service = KnowledgeGraphService()
        result = await service.build_graph(db=db_session, document_id=doc_a.id)

        # Should have the filtered document node
        doc_nodes = [n for n in result.nodes if n.type == "document"]
        assert any(n.id == f"doc_{doc_a.id}" for n in doc_nodes)

    async def test_build_graph_with_group_filter(
        self, db_session, test_group, test_documents_with_relationships
    ):
        """Test graph filtering by group_id."""
        service = KnowledgeGraphService()
        result = await service.build_graph(db=db_session, group_id=test_group.id)

        # All document nodes should be in this group
        doc_nodes = [n for n in result.nodes if n.type == "document"]
        assert len(doc_nodes) == 2

    async def test_build_graph_with_relationship_type_filter(
        self, db_session, test_documents_with_relationships
    ):
        """Test graph filtering by relationship type."""
        service = KnowledgeGraphService()
        result = await service.build_graph(
            db=db_session, relationship_type="references"
        )

        # Should have edges of type "references"
        ref_edges = [e for e in result.edges if e.type == "references"]
        assert len(ref_edges) >= 1

    async def test_build_graph_empty_db(self, db_session):
        """Test graph building with no data returns empty graph."""
        service = KnowledgeGraphService()
        result = await service.build_graph(db=db_session)

        assert result.nodes == []
        assert result.edges == []


@pytest.mark.asyncio
class TestKnowledgeGraphAPI:
    """Integration tests for knowledge graph API endpoints."""

    async def test_knowledge_graph_requires_auth(self, client: AsyncClient):
        """Test that endpoint requires authentication."""
        resp = await client.get("/api/knowledge-graph")
        assert resp.status_code == 401

    async def test_knowledge_graph_returns_data(
        self, client: AsyncClient, auth_token, test_documents_with_relationships
    ):
        """Test that knowledge graph endpoint returns nodes and edges."""
        resp = await client.get(
            "/api/knowledge-graph",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "nodes" in data
        assert "edges" in data
        assert len(data["nodes"]) > 0
        assert len(data["edges"]) > 0

    async def test_knowledge_graph_filter_by_group(
        self, client: AsyncClient, auth_token, test_group, test_documents_with_relationships
    ):
        """Test filtering graph by group_id."""
        resp = await client.get(
            "/api/knowledge-graph",
            params={"group_id": test_group.id},
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["nodes"]) > 0

    async def test_knowledge_graph_view_returns_html(
        self, client: AsyncClient, auth_token
    ):
        """Test that view endpoint returns HTML page with vis.js."""
        resp = await client.get(
            "/api/knowledge-graph/view",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        content = resp.text
        assert "vis-network" in content
        assert "Knowledge Graph" in content
        assert "loadGraph" in content
