import logging

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.llm import chat_completion, generate_embeddings
from app.models.document import Document
from app.schemas.search import (
    ChatRequest,
    ChatResponse,
    ChatSource,
    SearchRequest,
    SearchResponse,
    SearchResult,
)
from app.services.vectordb import VectorDBService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["search"])

vectordb_service = VectorDBService()


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

    # Build messages
    messages = []
    if request.history:
        messages.extend(request.history)
    messages.append({"role": "user", "content": request.query})

    # Call LLM
    answer = chat_completion(messages=messages, context=context)

    return ChatResponse(answer=answer, sources=sources)
