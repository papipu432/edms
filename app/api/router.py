from fastapi import APIRouter

from app.api.annotations import router as annotations_router
from app.api.auth import router as auth_router
from app.api.bulk import router as bulk_router
from app.api.documents import router as documents_router
from app.api.groups import router as groups_router
from app.api.ldap import router as ldap_router
from app.api.org import router as org_router
from app.api.pages import router as pages_router
from app.api.rbac import router as rbac_router
from app.api.scanner import router as scanner_router
from app.api.search import router as search_router
from app.api.settings_llm import router as settings_llm_router
from app.api.security import router as security_router
from app.api.settings_backup import router as settings_backup_router
from app.api.settings_encryption import router as settings_encryption_router
from app.api.users import router as users_router
from app.api.wiki import router as wiki_router
from app.api.workflow import router as workflow_router
from app.api.lifecycle import router as lifecycle_router

api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(users_router)
api_router.include_router(groups_router)
api_router.include_router(documents_router)
api_router.include_router(search_router)
api_router.include_router(wiki_router)
api_router.include_router(scanner_router)
api_router.include_router(annotations_router)
api_router.include_router(workflow_router)
api_router.include_router(bulk_router)
api_router.include_router(pages_router)
api_router.include_router(org_router)
api_router.include_router(rbac_router)
api_router.include_router(ldap_router)
api_router.include_router(settings_llm_router)
api_router.include_router(settings_backup_router)
api_router.include_router(security_router)
api_router.include_router(settings_encryption_router)
api_router.include_router(lifecycle_router)
