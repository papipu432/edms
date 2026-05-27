from fastapi import APIRouter

from app.api.documents import router as documents_router
from app.api.groups import router as groups_router

api_router = APIRouter()
api_router.include_router(groups_router)
api_router.include_router(documents_router)
