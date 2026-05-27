import logging

import chromadb

from app.core.config import settings

logger = logging.getLogger(__name__)

CHROMA_DB_PATH = settings.CHROMA_DB_PATH


def _create_chroma_client(
    persist_directory: str | None = None,
    host: str | None = None,
    port: int | None = None,
    auth_token: str | None = None,
) -> chromadb.ClientAPI:
    """Create a ChromaDB client based on configuration.

    If host is provided, creates an HTTP client connecting to a remote ChromaDB server.
    Otherwise, creates a PersistentClient using local file storage.
    """
    chroma_host = host if host is not None else settings.CHROMA_HOST
    chroma_port = port if port is not None else settings.CHROMA_PORT
    chroma_token = auth_token if auth_token is not None else settings.CHROMA_AUTH_TOKEN

    if chroma_host:
        headers: dict[str, str] = {}
        if chroma_token:
            headers["Authorization"] = f"Bearer {chroma_token}"
        logger.info("Connecting to ChromaDB at %s:%d", chroma_host, chroma_port)
        return chromadb.HttpClient(
            host=chroma_host,
            port=chroma_port,
            headers=headers,
        )

    path = persist_directory or CHROMA_DB_PATH
    return chromadb.PersistentClient(path=path)


class VectorDBService:
    """Service for managing document embeddings in ChromaDB."""

    def __init__(self, persist_directory: str | None = None) -> None:
        self.client = _create_chroma_client(persist_directory=persist_directory)
        self.collection = self.client.get_or_create_collection(
            name="documents",
            metadata={"hnsw:space": "cosine"},
        )

    def index_document(
        self,
        doc_id: int,
        group_id: int,
        chunks: list[str],
        embeddings: list[list[float]],
    ) -> None:
        """Index document chunks with their embeddings."""
        if not chunks:
            return

        ids = [f"doc_{doc_id}_chunk_{i}" for i in range(len(chunks))]
        metadatas = [
            {"doc_id": doc_id, "group_id": group_id, "chunk_index": i}
            for i in range(len(chunks))
        ]

        self.collection.upsert(
            ids=ids,
            documents=chunks,
            embeddings=embeddings,
            metadatas=metadatas,
        )
        logger.info("Indexed %d chunks for document %d", len(chunks), doc_id)

    def search(
        self,
        query_embedding: list[float],
        group_id: int | None = None,
        top_k: int = 5,
    ) -> list[dict]:
        """Search for similar chunks.

        Returns list of dicts with keys: chunk_text, doc_id, score.
        """
        where_filter = {"group_id": group_id} if group_id is not None else None

        try:
            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k,
                where=where_filter,
                include=["documents", "metadatas", "distances"],
            )
        except Exception as e:
            logger.error("Vector search failed: %s", e)
            return []

        items = []
        if results and results["documents"] and results["documents"][0]:
            documents = results["documents"][0]
            metadatas = results["metadatas"][0] if results["metadatas"] else []
            distances = results["distances"][0] if results["distances"] else []

            for i, doc_text in enumerate(documents):
                metadata = metadatas[i] if i < len(metadatas) else {}
                distance = distances[i] if i < len(distances) else 0.0
                # ChromaDB cosine distance: 0 = identical, 2 = opposite
                # Convert to similarity score: 1 - (distance / 2)
                score = 1.0 - (distance / 2.0)
                items.append(
                    {
                        "chunk_text": doc_text,
                        "doc_id": metadata.get("doc_id", 0),
                        "score": score,
                    }
                )

        return items

    def delete_document(self, doc_id: int) -> None:
        """Delete all chunks for a document."""
        try:
            # Get all IDs matching this doc_id
            results = self.collection.get(
                where={"doc_id": doc_id},
                include=[],
            )
            if results and results["ids"]:
                self.collection.delete(ids=results["ids"])
                logger.info("Deleted %d chunks for document %d", len(results["ids"]), doc_id)
        except Exception as e:
            logger.error("Failed to delete document %d from vector DB: %s", doc_id, e)
