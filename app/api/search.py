import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.llm import chat_completion, generate_embeddings
from app.core.security import get_current_user
from app.models.document import Document
from app.models.user import User
from app.schemas.search import (
    ChatRequest,
    ChatResponse,
    ChatSource,
    SearchRequest,
    SearchResponse,
    SearchResult,
)
from app.schemas.search_enhanced import (
    FacetedSearchRequest,
    FacetedSearchResponse,
    RelatedDocumentsResponse,
    SearchHistoryResponse,
    SuggestionsResponse,
)
from app.services.search_enhanced import EnhancedSearchService
from app.services.vectordb import VectorDBService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["search"])

vectordb_service = VectorDBService()
enhanced_search_service = EnhancedSearchService(vectordb_service=vectordb_service)


@router.post("/api/search", response_model=SearchResponse)
async def search_documents(
    request: SearchRequest,
    db: AsyncSession = Depends(get_db),
) -> SearchResponse:
    """Search for relevant document chunks."""
    # Generate embedding for the query
    embeddings = generate_embeddings([request.query])
    query_embedding = embeddings[0]

    # Search vector DB
    results = vectordb_service.search(
        query_embedding=query_embedding,
        group_id=request.group_id,
        top_k=request.top_k,
    )

    # Fetch document names
    search_results = []
    for item in results:
        doc_id = item["doc_id"]
        document = await db.get(Document, doc_id)
        doc_name = document.original_filename if document else "Unknown"
        search_results.append(
            SearchResult(
                chunk_text=item["chunk_text"],
                document_id=doc_id,
                document_name=doc_name,
                score=item["score"],
            )
        )

    return SearchResponse(results=search_results)


@router.post("/api/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    db: AsyncSession = Depends(get_db),
) -> ChatResponse:
    """RAG chat endpoint - retrieves context and generates an answer."""
    # Generate embedding for the query
    embeddings = generate_embeddings([request.query])
    query_embedding = embeddings[0]

    # Search for relevant chunks
    top_k = 5
    results = vectordb_service.search(
        query_embedding=query_embedding,
        group_id=request.group_id,
        top_k=top_k,
    )

    # Build context from retrieved chunks
    context_parts = []
    sources = []

    for item in results:
        doc_id = item["doc_id"]
        chunk_text = item["chunk_text"]
        context_parts.append(chunk_text)

        document = await db.get(Document, doc_id)
        doc_name = document.original_filename if document else "Unknown"
        sources.append(
            ChatSource(
                document_id=doc_id,
                document_name=doc_name,
                chunk_text=chunk_text,
            )
        )

    context = "\n\n---\n\n".join(context_parts)

    # Truncate context to prevent exceeding LLM token limits
    max_context_size = 50_000
    if len(context) > max_context_size:
        context = context[:max_context_size]

    # Build messages
    messages = []
    if request.history:
        messages.extend(request.history)
    messages.append({"role": "user", "content": request.query})

    # Call LLM
    answer = chat_completion(messages=messages, context=context)

    return ChatResponse(answer=answer, sources=sources)


@router.post("/api/search/faceted", response_model=FacetedSearchResponse)
async def faceted_search(
    request: FacetedSearchRequest,
    db: AsyncSession = Depends(get_db),
) -> FacetedSearchResponse:
    """Faceted search with multiple filters."""
    response = await enhanced_search_service.faceted_search(db, request)

    return response


@router.get("/api/search/suggestions", response_model=SuggestionsResponse)
async def search_suggestions(
    q: str = Query(..., min_length=1),
    db: AsyncSession = Depends(get_db),
) -> SuggestionsResponse:
    """Get search suggestions/autocomplete for a partial query."""
    return await enhanced_search_service.get_suggestions(db, q)


@router.get("/api/documents/{document_id}/related", response_model=RelatedDocumentsResponse)
async def get_related_documents(
    document_id: int,
    db: AsyncSession = Depends(get_db),
) -> RelatedDocumentsResponse:
    """Get related documents based on vector similarity."""
    return await enhanced_search_service.get_related_documents(db, document_id)


@router.get("/api/search/history", response_model=SearchHistoryResponse)
async def get_search_history(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SearchHistoryResponse:
    """Get current user's search history."""
    return await enhanced_search_service.get_search_history(db, current_user.id)


@router.delete("/api/search/history")
async def clear_search_history(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Clear current user's search history."""
    await enhanced_search_service.clear_search_history(db, current_user.id)
    return {"detail": "Search history cleared"}
