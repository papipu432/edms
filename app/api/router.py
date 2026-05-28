from fastapi import APIRouter

from app.api.access_request import router as access_request_router
from app.api.activity import router as activity_router
from app.api.annotations import router as annotations_router
from app.api.auth import router as auth_router
from app.api.breadcrumbs import router as breadcrumbs_router
from app.api.bulk import router as bulk_router
from app.api.canvas import router as canvas_router
from app.api.chat import router as chat_router
from app.api.command_palette import router as command_palette_router
from app.api.compare import router as compare_router
from app.api.daily_notes import router as daily_notes_router
from app.api.documents import router as documents_router
from app.api.expiry_prediction import router as expiry_prediction_router
from app.api.groups import router as groups_router
from app.api.health import router as health_router
from app.api.health_dashboard import router as health_dashboard_router
from app.api.kanban import router as kanban_router
from app.api.compliance import router as compliance_router
from app.api.geofence import router as geofence_router
from app.api.knowledge_graph import router as knowledge_graph_router
from app.api.sessions import router as sessions_router
from app.api.watermark import router as watermark_router
from app.api.ldap import router as ldap_router
from app.api.lifecycle import router as lifecycle_router
from app.api.obsidian import router as obsidian_router
from app.api.obsidian_sync import router as obsidian_sync_router
from app.api.onboarding import router as onboarding_router
from app.api.org import router as org_router
from app.api.pages import router as pages_router
from app.api.preview import router as preview_router
from app.api.rbac import router as rbac_router
from app.api.relationships import router as relationships_router
from app.api.scanner import router as scanner_router
from app.api.search import router as search_router
from app.api.security import router as security_router
from app.api.settings_backup import router as settings_backup_router
from app.api.settings_encryption import router as settings_encryption_router
from app.api.settings_llm import router as settings_llm_router
from app.api.smart_folders import router as smart_folders_router
from app.api.tags import router as tags_router
from app.api.templates import router as templates_router
from app.api.users import router as users_router
from app.api.versions import router as versions_router
from app.api.websocket import router as notifications_router
from app.api.wiki import router as wiki_router
from app.api.wiki_graph import router as wiki_graph_router
from app.api.workflow import router as workflow_router
from app.api.approval_chains import router as approval_chains_router
from app.api.audit import router as audit_router
from app.api.comments import router as comments_router
from app.api.delegations import router as delegations_router
from app.api.document_locks import router as document_locks_router
from app.api.signatures import router as signatures_router
from app.api.sla import router as sla_router
from app.api.health_score import router as health_score_router
from app.api.scheduled_reports import router as scheduled_reports_router
from app.api.tenants import router as tenants_router
from app.api.offline import router as offline_router
from app.api.import_export import router as import_export_router
from app.api.webhooks import router as webhooks_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(auth_router)
api_router.include_router(users_router)
api_router.include_router(groups_router)
api_router.include_router(compare_router)
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
api_router.include_router(relationships_router)
api_router.include_router(health_dashboard_router)
api_router.include_router(obsidian_router)
api_router.include_router(chat_router)
api_router.include_router(audit_router)
api_router.include_router(versions_router)
api_router.include_router(preview_router)
api_router.include_router(notifications_router)
api_router.include_router(tags_router)
api_router.include_router(smart_folders_router)
api_router.include_router(templates_router)
api_router.include_router(command_palette_router)
api_router.include_router(activity_router)
api_router.include_router(kanban_router)
api_router.include_router(breadcrumbs_router)
api_router.include_router(expiry_prediction_router)
api_router.include_router(onboarding_router)
api_router.include_router(approval_chains_router)
api_router.include_router(comments_router)
api_router.include_router(document_locks_router)
api_router.include_router(signatures_router)
api_router.include_router(delegations_router)
api_router.include_router(sla_router)
api_router.include_router(knowledge_graph_router)
api_router.include_router(compliance_router)
api_router.include_router(geofence_router)
api_router.include_router(watermark_router)
api_router.include_router(access_request_router)
api_router.include_router(sessions_router)
api_router.include_router(obsidian_sync_router)
api_router.include_router(daily_notes_router)
api_router.include_router(wiki_graph_router)
api_router.include_router(canvas_router)
api_router.include_router(health_score_router)
api_router.include_router(scheduled_reports_router)
api_router.include_router(tenants_router)
api_router.include_router(offline_router)
api_router.include_router(import_export_router)
api_router.include_router(webhooks_router)
