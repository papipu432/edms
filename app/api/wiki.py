from fastapi import APIRouter, HTTPException

from app.core.config import settings
from app.schemas.wiki import (
    WikiIndexResponse,
    WikiLintResponse,
    WikiLogResponse,
    WikiPageResponse,
    WikiQueryRequest,
    WikiQueryResponse,
)
from app.services.wiki import WikiService

router = APIRouter(prefix="/api/wiki", tags=["wiki"])

wiki_service = WikiService(wiki_path=settings.WIKI_PATH)


@router.get("/index", response_model=WikiIndexResponse)
async def get_wiki_index():
    """Return wiki index content and list of all wiki page paths."""
    content, pages = wiki_service.get_index()
    return WikiIndexResponse(content=content, pages=pages)


@router.get("/pages/{page_path:path}", response_model=WikiPageResponse)
async def get_wiki_page(page_path: str):
    """Return content of a specific wiki page."""
    content = wiki_service.get_page(page_path)
    if content is None:
        raise HTTPException(status_code=404, detail="Wiki page not found")
    return WikiPageResponse(path=page_path, content=content)


@router.post("/query", response_model=WikiQueryResponse)
async def query_wiki(request: WikiQueryRequest):
    """Ask a question and get an answer synthesized from wiki pages."""
    answer = wiki_service.query(request.question)
    # Extract source references from the answer context
    _, pages = wiki_service.get_index()
    sources = [p for p in pages if any(part in answer.lower() for part in p.replace(".md", "").split("/")[-1:])]
    return WikiQueryResponse(answer=answer, sources=sources)


@router.post("/lint", response_model=WikiLintResponse)
async def lint_wiki():
    """Run wiki lint and return issues found."""
    issues = wiki_service.lint()
    return WikiLintResponse(issues=issues)


@router.get("/log", response_model=WikiLogResponse)
async def get_wiki_log():
    """Return recent operations from log.md."""
    entries = wiki_service.get_log()
    return WikiLogResponse(entries=entries)
