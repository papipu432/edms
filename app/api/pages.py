from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

router = APIRouter(tags=["pages"])
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


@router.get("/")
async def root(request: Request):
    return templates.TemplateResponse(request, "login.html")


@router.get("/login")
async def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html")


@router.get("/register")
async def register_page(request: Request):
    return templates.TemplateResponse(request, "register.html")


@router.get("/dashboard")
async def dashboard_page(request: Request):
    return templates.TemplateResponse(request, "dashboard.html")


@router.get("/documents/{document_id}/view")
async def document_viewer_page(request: Request, document_id: int):
    return templates.TemplateResponse(
        request, "document_viewer.html", {"document_id": document_id}
    )


@router.get("/workflow")
async def workflow_page(request: Request):
    return templates.TemplateResponse(request, "workflow.html")


@router.get("/documents/{document_id}/crossref")
async def crossref_page(request: Request, document_id: int):
    return templates.TemplateResponse(
        request, "crossref.html", {"document_id": document_id}
    )


@router.get("/kanban")
async def kanban_page(request: Request):
    return templates.TemplateResponse(request, "kanban.html")


@router.get("/documents/{document_id}/pdf")
async def pdf_viewer_page(request: Request, document_id: int):
    return templates.TemplateResponse(
        request, "pdf_viewer.html", {"document_id": document_id}
    )


@router.get("/activity")
async def activity_page(request: Request):
    return templates.TemplateResponse(request, "activity.html")


@router.get("/tags")
async def tags_page(request: Request):
    return templates.TemplateResponse(request, "tags.html")


@router.get("/templates")
async def templates_page(request: Request):
    return templates.TemplateResponse(request, "templates.html")


@router.get("/admin/users")
async def admin_users_page(request: Request):
    return templates.TemplateResponse(request, "admin_users.html")


@router.get("/workflow-builder")
async def workflow_builder_page(request: Request):
    return templates.TemplateResponse(request, "workflow_builder.html")
