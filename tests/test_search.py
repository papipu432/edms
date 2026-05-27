from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import get_db
from app.main import app
from app.models.document import Document, DocumentStatus
from app.models.group import Base, Group
from app.services.chunker import split_text
from app.services.vectordb import VectorDBService


# --- Chunker Tests ---


class TestChunker:
    def test_split_text_basic(self):
        """Test basic text splitting."""
        text = "Hello world. " * 200  # ~2600 chars
        chunks = split_text(text, chunk_size=1000, overlap=200)
        assert len(chunks) > 1
        for chunk in chunks:
            assert len(chunk) <= 1000

    def test_split_text_with_overlap(self):
        """Test that chunks have overlapping content."""
        # Create text with clear paragraph separators
        paragraphs = [f"Paragraph {i}. " * 50 for i in range(10)]
        text = "\n\n".join(paragraphs)
        chunks = split_text(text, chunk_size=500, overlap=100)
        assert len(chunks) > 1
        # Check that some content overlaps between adjacent chunks
        for i in range(len(chunks) - 1):
            # Verify each chunk respects max size
            assert len(chunks[i]) <= 500

    def test_split_text_empty(self):
        """Test that empty text returns empty list."""
        result = split_text("")
        assert result == []

    def test_split_text_short(self):
        """Test that short text returns single chunk."""
        result = split_text("Short text", chunk_size=1000, overlap=200)
        assert len(result) == 1
        assert result[0] == "Short text"

    def test_split_text_respects_chunk_size(self):
        """Test that all chunks respect max size."""
        text = "Word " * 2000  # 10000 chars
        chunks = split_text(text, chunk_size=500, overlap=50)
        for chunk in chunks:
            assert len(chunk) <= 500


# --- VectorDB Tests ---


class TestVectorDBService:
    def test_index_and_search(self, tmp_path):
        """Test indexing documents and searching."""
        service = VectorDBService(persist_directory=str(tmp_path / "chroma_test"))

        # Create fake embeddings (1536 dimensions for consistency)
        chunks = ["This is chunk one about Python.", "This is chunk two about FastAPI."]
        embeddings = [[0.1] * 1536, [0.2] * 1536]

        service.index_document(
            doc_id=1,
            group_id=1,
            chunks=chunks,
            embeddings=embeddings,
        )

        # Search with a query embedding close to first chunk
        results = service.search(
            query_embedding=[0.1] * 1536,
            top_k=2,
        )
        assert len(results) > 0
        assert results[0]["doc_id"] == 1
        assert "chunk" in results[0]["chunk_text"].lower()

    def test_search_with_group_filter(self, tmp_path):
        """Test that group_id filtering works."""
        service = VectorDBService(persist_directory=str(tmp_path / "chroma_filter"))

        # Index documents in different groups
        service.index_document(
            doc_id=1, group_id=1,
            chunks=["Group one content"],
            embeddings=[[0.1] * 1536],
        )
        service.index_document(
            doc_id=2, group_id=2,
            chunks=["Group two content"],
            embeddings=[[0.2] * 1536],
        )

        # Search filtered by group 1
        results = service.search(
            query_embedding=[0.1] * 1536,
            group_id=1,
            top_k=5,
        )
        assert len(results) == 1
        assert results[0]["doc_id"] == 1

    def test_delete_document(self, tmp_path):
        """Test deleting a document from the index."""
        service = VectorDBService(persist_directory=str(tmp_path / "chroma_delete"))

        service.index_document(
            doc_id=1, group_id=1,
            chunks=["Content to delete"],
            embeddings=[[0.5] * 1536],
        )

        # Verify it exists
        results = service.search(query_embedding=[0.5] * 1536, top_k=5)
        assert len(results) == 1

        # Delete
        service.delete_document(doc_id=1)

        # Verify it's gone
        results = service.search(query_embedding=[0.5] * 1536, top_k=5)
        assert len(results) == 0

    def test_index_empty_chunks(self, tmp_path):
        """Test that indexing empty chunks does nothing."""
        service = VectorDBService(persist_directory=str(tmp_path / "chroma_empty"))
        # Should not raise
        service.index_document(doc_id=1, group_id=1, chunks=[], embeddings=[])


# --- API Endpoint Tests ---


@pytest_asyncio.fixture
async def search_db_session(tmp_path):
    """Create a DB session for search tests."""
    db_path = tmp_path / "search_test.db"
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
async def search_client(search_db_session: AsyncSession, tmp_path):
    """Create a test client with mocked vector DB and LLM."""
    from collections.abc import AsyncGenerator

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        try:
            yield search_db_session
            await search_db_session.commit()
        except Exception:
            await search_db_session.rollback()
            raise

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


class TestSearchEndpoint:
    @pytest.mark.asyncio
    async def test_search_returns_results(self, search_client, search_db_session):
        """Test POST /api/search returns search results."""
        # Create a group and document in the DB
        group = Group(name="Search Test Group")
        search_db_session.add(group)
        await search_db_session.flush()
        await search_db_session.refresh(group)

        document = Document(
            group_id=group.id,
            original_filename="test.pdf",
            storage_path="/fake/path",
            file_type="application/pdf",
            file_size=1000,
            status=DocumentStatus.processed,
        )
        search_db_session.add(document)
        await search_db_session.flush()
        await search_db_session.refresh(document)

        # Mock embeddings and vector DB search
        mock_search_results = [
            {
                "chunk_text": "This is relevant content.",
                "doc_id": document.id,
                "score": 0.95,
            }
        ]

        with patch(
            "app.api.search.generate_embeddings",
            return_value=[[0.1] * 1536],
        ), patch.object(
            VectorDBService,
            "search",
            return_value=mock_search_results,
        ):
            response = await search_client.post(
                "/api/search",
                json={"query": "relevant content", "top_k": 5},
            )

        assert response.status_code == 200
        data = response.json()
        assert "results" in data
        assert len(data["results"]) == 1
        assert data["results"][0]["document_name"] == "test.pdf"
        assert data["results"][0]["score"] == 0.95

    @pytest.mark.asyncio
    async def test_search_with_group_filter(self, search_client, search_db_session):
        """Test POST /api/search with group_id filter."""
        group = Group(name="Filtered Group")
        search_db_session.add(group)
        await search_db_session.flush()
        await search_db_session.refresh(group)

        with patch(
            "app.api.search.generate_embeddings",
            return_value=[[0.1] * 1536],
        ), patch.object(
            VectorDBService,
            "search",
            return_value=[],
        ):
            response = await search_client.post(
                "/api/search",
                json={"query": "test", "group_id": group.id, "top_k": 3},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["results"] == []


class TestChatEndpoint:
    @pytest.mark.asyncio
    async def test_chat_returns_answer(self, search_client, search_db_session):
        """Test POST /api/chat returns generated answer with sources."""
        group = Group(name="Chat Test Group")
        search_db_session.add(group)
        await search_db_session.flush()
        await search_db_session.refresh(group)

        document = Document(
            group_id=group.id,
            original_filename="chat_doc.pdf",
            storage_path="/fake/path",
            file_type="application/pdf",
            file_size=2000,
            status=DocumentStatus.processed,
        )
        search_db_session.add(document)
        await search_db_session.flush()
        await search_db_session.refresh(document)

        mock_search_results = [
            {
                "chunk_text": "The capital of France is Paris.",
                "doc_id": document.id,
                "score": 0.9,
            }
        ]

        with patch(
            "app.api.search.generate_embeddings",
            return_value=[[0.1] * 1536],
        ), patch.object(
            VectorDBService,
            "search",
            return_value=mock_search_results,
        ), patch(
            "app.api.search.chat_completion",
            return_value="The capital of France is Paris.",
        ):
            response = await search_client.post(
                "/api/chat",
                json={"query": "What is the capital of France?"},
            )

        assert response.status_code == 200
        data = response.json()
        assert "answer" in data
        assert data["answer"] == "The capital of France is Paris."
        assert "sources" in data
        assert len(data["sources"]) == 1
        assert data["sources"][0]["document_name"] == "chat_doc.pdf"

    @pytest.mark.asyncio
    async def test_chat_with_history(self, search_client, search_db_session):
        """Test POST /api/chat with conversation history."""
        group = Group(name="History Test Group")
        search_db_session.add(group)
        await search_db_session.flush()
        await search_db_session.refresh(group)

        with patch(
            "app.api.search.generate_embeddings",
            return_value=[[0.1] * 1536],
        ), patch.object(
            VectorDBService,
            "search",
            return_value=[],
        ), patch(
            "app.api.search.chat_completion",
            return_value="I could not find relevant information.",
        ):
            response = await search_client.post(
                "/api/chat",
                json={
                    "query": "Tell me more",
                    "history": [
                        {"role": "user", "content": "What is Python?"},
                        {"role": "assistant", "content": "Python is a programming language."},
                    ],
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert "answer" in data
        assert data["sources"] == []
