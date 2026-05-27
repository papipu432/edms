from fastapi import APIRouter

from app.api.documents import router as documents_router
from app.api.groups import router as groups_router
from app.api.scanner import router as scanner_router
from app.api.search import router as search_router
from app.api.wiki import router as wiki_router

api_router = APIRouter()
api_router.include_router(groups_router)
api_router.include_router(documents_router)
api_router.include_router(search_router)
api_router.include_router(wiki_router)
api_router.include_router(scanner_router)
