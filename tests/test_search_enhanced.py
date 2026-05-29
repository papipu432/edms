from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import get_db
from app.core.security import get_current_user
from app.main import app
from app.models.document import Document, DocumentStatus
from app.models.group import Base, Group
from app.models.lifecycle import DocumentLifecycle, DocumentLifecycleState, LifecycleType
from app.models.user import User
from app.services.search_enhanced import EnhancedSearchService


@pytest_asyncio.fixture
async def enhanced_db_session(tmp_path):
    """Create a DB session for enhanced search tests."""
    db_path = tmp_path / "enhanced_search_test.db"
    db_url = f"sqlite+aiosqlite:///{db_path}"
    engine = create_async_engine(db_url, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest_asyncio.fixture
async def test_user(enhanced_db_session: AsyncSession):
    """Create a test user."""
    user = User(
        id="test-user-123",
        username="testuser",
        display_name="Test User",
        email="test@example.com",
        hashed_password="fakehash",
        is_active=True,
    )
    enhanced_db_session.add(user)
    await enhanced_db_session.flush()
    await enhanced_db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def enhanced_client(enhanced_db_session: AsyncSession, test_user: User, tmp_path):
    """Create a test client for enhanced search tests."""
    from collections.abc import AsyncGenerator

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        try:
            yield enhanced_db_session
            await enhanced_db_session.commit()
        except Exception:
            await enhanced_db_session.rollback()
            raise

    async def override_get_current_user() -> User:
        return test_user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def sample_documents(enhanced_db_session: AsyncSession):
    """Create sample documents for testing."""
    group1 = Group(name="Engineering")
    group2 = Group(name="Marketing")
    enhanced_db_session.add_all([group1, group2])
    await enhanced_db_session.flush()
    await enhanced_db_session.refresh(group1)
    await enhanced_db_session.refresh(group2)

    now = datetime.utcnow()
    doc1 = Document(
        group_id=group1.id,
        original_filename="python_guide.pdf",
        storage_path="/fake/path1",
        file_type="application/pdf",
        file_size=1000,
        status=DocumentStatus.processed,
        keywords=["python", "programming", "tutorial"],
        created_at=now - timedelta(days=5),
    )
    doc2 = Document(
        group_id=group1.id,
        original_filename="fastapi_docs.pdf",
        storage_path="/fake/path2",
        file_type="application/pdf",
        file_size=2000,
        status=DocumentStatus.processed,
        keywords=["fastapi", "api", "python"],
        created_at=now - timedelta(days=2),
    )
    doc3 = Document(
        group_id=group2.id,
        original_filename="marketing_plan.docx",
        storage_path="/fake/path3",
        file_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        file_size=3000,
        status=DocumentStatus.processed,
        keywords=["marketing", "strategy", "plan"],
        created_at=now - timedelta(days=10),
    )
    enhanced_db_session.add_all([doc1, doc2, doc3])
    await enhanced_db_session.flush()
    await enhanced_db_session.refresh(doc1)
    await enhanced_db_session.refresh(doc2)
    await enhanced_db_session.refresh(doc3)

    # Add lifecycle for doc1
    lifecycle = DocumentLifecycle(
        document_id=doc1.id,
        lifecycle_type=LifecycleType.permanent,
        state=DocumentLifecycleState.approved,
    )
    enhanced_db_session.add(lifecycle)
    await enhanced_db_session.flush()

    return {"group1": group1, "group2": group2, "doc1": doc1, "doc2": doc2, "doc3": doc3}


class TestFacetedSearch:
    @pytest.mark.asyncio
    async def test_faceted_search_filters_by_group(
        self, enhanced_client, sample_documents
    ):
        """Test faceted search filtering by group_id."""
        group1 = sample_documents["group1"]
        response = await enhanced_client.post(
            "/api/search/faceted",
            json={"group_id": group1.id},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total_count"] == 2
        assert len(data["results"]) == 2
        for result in data["results"]:
            assert result["group_id"] == group1.id
        assert "facets" in data
        assert "groups" in data["facets"]
        assert "file_types" in data["facets"]

    @pytest.mark.asyncio
    async def test_faceted_search_by_date_range(
        self, enhanced_client, sample_documents
    ):
        """Test faceted search filtering by date range."""
        now = datetime.utcnow()
        date_from = (now - timedelta(days=3)).isoformat()
        date_to = now.isoformat()

        response = await enhanced_client.post(
            "/api/search/faceted",
            json={"date_from": date_from, "date_to": date_to},
        )
        assert response.status_code == 200
        data = response.json()
        # Should include doc2 (2 days ago) but not doc1 (5 days ago) or doc3 (10 days ago)
        assert data["total_count"] == 1
        assert data["results"][0]["document_name"] == "fastapi_docs.pdf"

    @pytest.mark.asyncio
    async def test_faceted_search_by_file_type(
        self, enhanced_client, sample_documents
    ):
        """Test faceted search filtering by file_type."""
        response = await enhanced_client.post(
            "/api/search/faceted",
            json={"file_type": "application/pdf"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total_count"] == 2
        for result in data["results"]:
            assert result["file_type"] == "application/pdf"

    @pytest.mark.asyncio
    async def test_faceted_search_returns_facets(
        self, enhanced_client, sample_documents
    ):
        """Test that faceted search always returns facet counts."""
        response = await enhanced_client.post(
            "/api/search/faceted",
            json={},
        )
        assert response.status_code == 200
        data = response.json()
        assert "facets" in data
        facets = data["facets"]
        assert "groups" in facets
        assert "file_types" in facets
        assert "lifecycle_states" in facets
        # Should have entries for our documents
        assert len(facets["file_types"]) >= 1

    @pytest.mark.asyncio
    async def test_faceted_search_pagination(
        self, enhanced_client, sample_documents
    ):
        """Test faceted search pagination."""
        response = await enhanced_client.post(
            "/api/search/faceted",
            json={"page": 1, "page_size": 2},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["page"] == 1
        assert data["page_size"] == 2
        assert len(data["results"]) == 2
        assert data["total_count"] == 3


class TestSearchSuggestions:
    @pytest.mark.asyncio
    async def test_suggestions_return_matching_names(
        self, enhanced_client, sample_documents
    ):
        """Test suggestions return documents matching partial query."""
        response = await enhanced_client.get(
            "/api/search/suggestions", params={"q": "python"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "suggestions" in data
        assert len(data["suggestions"]) > 0
        texts = [s["text"] for s in data["suggestions"]]
        # Should match "python_guide.pdf" from document names
        assert any("python" in t.lower() for t in texts)

    @pytest.mark.asyncio
    async def test_suggestions_return_matching_keywords(
        self, enhanced_client, sample_documents
    ):
        """Test suggestions return keywords matching partial query."""
        response = await enhanced_client.get(
            "/api/search/suggestions", params={"q": "market"}
        )
        assert response.status_code == 200
        data = response.json()
        suggestions = data["suggestions"]
        assert len(suggestions) > 0
        sources = [s["source"] for s in suggestions]
        # Should have keyword source or document_name source
        assert any(s in ("keyword", "document_name") for s in sources)


class TestRelatedDocuments:
    @pytest.mark.asyncio
    async def test_related_documents_uses_similarity(
        self, enhanced_client, enhanced_db_session, sample_documents
    ):
        """Test related documents endpoint returns similar documents."""
        doc1 = sample_documents["doc1"]
        doc2 = sample_documents["doc2"]

        # Mock the vectordb collection
        mock_collection = MagicMock()
        mock_collection.get.return_value = {
            "ids": [f"doc_{doc1.id}_chunk_0"],
            "embeddings": [[0.1] * 1536],
        }
        mock_collection.query.return_value = {
            "metadatas": [[
                {"doc_id": doc1.id, "group_id": 1},
                {"doc_id": doc2.id, "group_id": 1},
            ]],
            "distances": [[0.1, 0.3]],
        }

        with patch(
            "app.api.search.enhanced_search_service.vectordb_service.collection",
            mock_collection,
        ):
            response = await enhanced_client.get(
                f"/api/documents/{doc1.id}/related"
            )

        assert response.status_code == 200
        data = response.json()
        assert data["document_id"] == doc1.id
        assert "related" in data
        # Should find doc2 as related (doc1 itself is excluded)
        assert len(data["related"]) > 0
        related_ids = [r["document_id"] for r in data["related"]]
        assert doc2.id in related_ids

    @pytest.mark.asyncio
    async def test_related_documents_empty_when_no_vectors(
        self, enhanced_client, sample_documents
    ):
        """Test related documents returns empty when no vectors exist."""
        doc1 = sample_documents["doc1"]

        mock_collection = MagicMock()
        mock_collection.get.return_value = {
            "ids": [],
            "embeddings": [],
        }

        with patch(
            "app.api.search.enhanced_search_service.vectordb_service.collection",
            mock_collection,
        ):
            response = await enhanced_client.get(
                f"/api/documents/{doc1.id}/related"
            )

        assert response.status_code == 200
        data = response.json()
        assert data["related"] == []


class TestSearchHistory:
    @pytest.mark.asyncio
    async def test_search_history_saved_and_retrieved(
        self, enhanced_client, enhanced_db_session, test_user
    ):
        """Test search history is saved and can be retrieved."""
        # Save history entries directly via service
        service = EnhancedSearchService()
        await service.save_search_history(
            enhanced_db_session, test_user.id, "python tutorial", None, 5
        )
        await service.save_search_history(
            enhanced_db_session,
            test_user.id,
            "fastapi guide",
            {"group_id": 1},
            3,
        )
        await enhanced_db_session.commit()

        # Retrieve via API
        response = await enhanced_client.get("/api/search/history")
        assert response.status_code == 200
        data = response.json()
        assert "history" in data
        assert len(data["history"]) == 2
        # Both entries are present
        query_texts = {item["query_text"] for item in data["history"]}
        assert "python tutorial" in query_texts
        assert "fastapi guide" in query_texts
        # Verify result counts
        results_map = {item["query_text"]: item["results_count"] for item in data["history"]}
        assert results_map["python tutorial"] == 5
        assert results_map["fastapi guide"] == 3

    @pytest.mark.asyncio
    async def test_search_history_cleared(
        self, enhanced_client, enhanced_db_session, test_user
    ):
        """Test that search history can be cleared."""
        # Save some history
        service = EnhancedSearchService()
        await service.save_search_history(
            enhanced_db_session, test_user.id, "test query", None, 1
        )
        await enhanced_db_session.commit()

        # Verify it exists
        response = await enhanced_client.get("/api/search/history")
        assert response.status_code == 200
        assert len(response.json()["history"]) == 1

        # Clear history
        response = await enhanced_client.delete("/api/search/history")
        assert response.status_code == 200
        assert response.json()["detail"] == "Search history cleared"

        # Verify it's empty
        response = await enhanced_client.get("/api/search/history")
        assert response.status_code == 200
        assert len(response.json()["history"]) == 0

    @pytest.mark.asyncio
    async def test_search_history_requires_auth(self, enhanced_db_session, tmp_path):
        """Test that search history endpoints require authentication."""
        from collections.abc import AsyncGenerator

        async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
            try:
                yield enhanced_db_session
                await enhanced_db_session.commit()
            except Exception:
                await enhanced_db_session.rollback()
                raise

        app.dependency_overrides[get_db] = override_get_db
        # Remove the current_user override so auth is required
        app.dependency_overrides.pop(get_current_user, None)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get("/api/search/history")
            assert response.status_code == 401

            response = await ac.delete("/api/search/history")
            assert response.status_code == 401

        app.dependency_overrides.clear()
