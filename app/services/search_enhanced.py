import logging

from sqlalchemy import String as SAString, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.models.lifecycle import DocumentLifecycle, DocumentLifecycleState
from app.models.search_history import SearchHistory
from app.schemas.search_enhanced import (
    FacetedSearchRequest,
    FacetedSearchResponse,
    FacetedSearchResult,
    RelatedDocument,
    RelatedDocumentsResponse,
    SearchHistoryItem,
    SearchHistoryResponse,
    SearchSuggestion,
    SuggestionsResponse,
)
from app.services.vectordb import VectorDBService

logger = logging.getLogger(__name__)


class EnhancedSearchService:
    def __init__(self, vectordb_service: VectorDBService | None = None) -> None:
        self.vectordb_service = vectordb_service

    async def faceted_search(
        self, db: AsyncSession, request: FacetedSearchRequest
    ) -> FacetedSearchResponse:
        """Perform faceted search with SQL filters and optional vector similarity."""
        # Build base query with optional lifecycle join
        query = select(Document).outerjoin(
            DocumentLifecycle, DocumentLifecycle.document_id == Document.id
        )

        # Apply filters
        if request.group_id is not None:
            query = query.where(Document.group_id == request.group_id)

        if request.file_type is not None:
            query = query.where(Document.file_type == request.file_type)

        if request.lifecycle_state is not None:
            query = query.where(
                DocumentLifecycle.state == DocumentLifecycleState(request.lifecycle_state)
            )

        if request.date_from is not None:
            query = query.where(Document.created_at >= request.date_from)

        if request.date_to is not None:
            query = query.where(Document.created_at <= request.date_to)

        if request.keywords:
            for kw in request.keywords:
                # For SQLite compatibility, use LIKE on the JSON field cast to string
                query = query.where(
                    func.cast(Document.keywords, SAString()).like(f"%{kw}%")
                )

        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total_count = total_result.scalar() or 0

        # Apply pagination
        offset = (request.page - 1) * request.page_size
        query = query.order_by(Document.created_at.desc())
        query = query.offset(offset).limit(request.page_size)

        result = await db.execute(query)
        documents = result.scalars().all()

        # Build results
        results = [
            FacetedSearchResult(
                document_id=doc.id,
                document_name=doc.original_filename,
                group_id=doc.group_id,
                file_type=doc.file_type,
                created_at=doc.created_at,
                score=None,
            )
            for doc in documents
        ]

        # Compute facets (always computed regardless of filters)
        facets = await self._compute_facets(db)

        return FacetedSearchResponse(
            results=results,
            facets=facets,
            total_count=total_count,
            page=request.page,
            page_size=request.page_size,
        )

    async def _compute_facets(self, db: AsyncSession) -> dict:
        """Compute facet counts for groups, file types, and lifecycle states."""
        facets: dict = {}

        # Group facets
        group_query = select(
            Document.group_id, func.count(Document.id)
        ).group_by(Document.group_id)
        group_result = await db.execute(group_query)
        facets["groups"] = {
            str(row[0]): row[1] for row in group_result.all()
        }

        # File type facets
        type_query = select(
            Document.file_type, func.count(Document.id)
        ).group_by(Document.file_type)
        type_result = await db.execute(type_query)
        facets["file_types"] = {
            row[0]: row[1] for row in type_result.all()
        }

        # Lifecycle state facets
        state_query = select(
            DocumentLifecycle.state, func.count(DocumentLifecycle.id)
        ).group_by(DocumentLifecycle.state)
        state_result = await db.execute(state_query)
        facets["lifecycle_states"] = {
            row[0].value if row[0] else "none": row[1] for row in state_result.all()
        }

        return facets

    async def get_suggestions(
        self, db: AsyncSession, partial_query: str
    ) -> SuggestionsResponse:
        """Get search suggestions from document names and keywords."""
        suggestions: list[SearchSuggestion] = []
        pattern = f"%{partial_query}%"

        # Search document names
        name_query = select(Document.original_filename).where(
            Document.original_filename.ilike(pattern)
        ).limit(5)
        name_result = await db.execute(name_query)
        for row in name_result.scalars().all():
            suggestions.append(
                SearchSuggestion(text=row, source="document_name")
            )

        # Search keywords (using LIKE on JSON field for SQLite compat)
        kw_query = select(Document.keywords).where(
            func.cast(Document.keywords, SAString()).like(pattern)
        ).limit(10)
        kw_result = await db.execute(kw_query)
        seen_keywords: set[str] = set()
        for kw_json in kw_result.scalars().all():
            if kw_json and isinstance(kw_json, list):
                for kw in kw_json:
                    if (
                        isinstance(kw, str)
                        and partial_query.lower() in kw.lower()
                        and kw not in seen_keywords
                    ):
                        seen_keywords.add(kw)
                        suggestions.append(
                            SearchSuggestion(text=kw, source="keyword")
                        )

        # Limit total suggestions
        return SuggestionsResponse(suggestions=suggestions[:10])

    async def get_related_documents(
        self, db: AsyncSession, doc_id: int, top_k: int = 5
    ) -> RelatedDocumentsResponse:
        """Find related documents using vector similarity."""
        related: list[RelatedDocument] = []

        if self.vectordb_service is None:
            return RelatedDocumentsResponse(document_id=doc_id, related=related)

        try:
            # Get chunks for this document from vector DB
            collection = self.vectordb_service.collection
            doc_results = collection.get(
                where={"doc_id": doc_id},
                include=["embeddings"],
            )

            if not doc_results or not doc_results["ids"] or not doc_results["embeddings"]:
                return RelatedDocumentsResponse(document_id=doc_id, related=related)

            # Use first chunk embedding as representative
            query_embedding = doc_results["embeddings"][0]

            # Search for similar chunks excluding our document
            search_results = collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k * 3,  # Get extra to allow deduplication
                include=["metadatas", "distances"],
            )

            if not search_results or not search_results["metadatas"]:
                return RelatedDocumentsResponse(document_id=doc_id, related=related)

            # Deduplicate by document ID
            seen_doc_ids: set[int] = set()
            metadatas = search_results["metadatas"][0] if search_results["metadatas"] else []
            distances = search_results["distances"][0] if search_results["distances"] else []

            for i, metadata in enumerate(metadatas):
                related_doc_id = metadata.get("doc_id", 0)
                if related_doc_id == doc_id or related_doc_id in seen_doc_ids:
                    continue
                seen_doc_ids.add(related_doc_id)

                distance = distances[i] if i < len(distances) else 0.0
                score = 1.0 - (distance / 2.0)

                # Get document name
                document = await db.get(Document, related_doc_id)
                if document:
                    related.append(
                        RelatedDocument(
                            document_id=related_doc_id,
                            document_name=document.original_filename,
                            similarity_score=score,
                        )
                    )

                if len(related) >= top_k:
                    break

        except Exception as e:
            logger.error("Failed to get related documents for %d: %s", doc_id, e)

        return RelatedDocumentsResponse(document_id=doc_id, related=related)

    async def save_search_history(
        self,
        db: AsyncSession,
        user_id: str,
        query: str,
        filters: dict | None,
        results_count: int,
    ) -> None:
        """Save a search to user's history."""
        history_entry = SearchHistory(
            user_id=user_id,
            query_text=query,
            filters_json=filters,
            results_count=results_count,
        )
        db.add(history_entry)
        await db.flush()

    async def get_search_history(
        self, db: AsyncSession, user_id: str, limit: int = 50
    ) -> SearchHistoryResponse:
        """Get user's search history."""
        query = (
            select(SearchHistory)
            .where(SearchHistory.user_id == user_id)
            .order_by(SearchHistory.searched_at.desc())
            .limit(limit)
        )
        result = await db.execute(query)
        entries = result.scalars().all()

        history = [
            SearchHistoryItem(
                id=entry.id,
                query_text=entry.query_text,
                filters_json=entry.filters_json,
                results_count=entry.results_count,
                searched_at=entry.searched_at,
            )
            for entry in entries
        ]

        return SearchHistoryResponse(history=history)

    async def clear_search_history(self, db: AsyncSession, user_id: str) -> None:
        """Clear all search history for a user."""
        query = select(SearchHistory).where(SearchHistory.user_id == user_id)
        result = await db.execute(query)
        entries = result.scalars().all()
        for entry in entries:
            await db.delete(entry)
        await db.flush()
