from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.template import DocumentTemplate
from app.models.user import User
from app.schemas.template import TemplateCreate, TemplateResponse, TemplateUpdate

router = APIRouter(tags=["templates"])


@router.post("/api/templates", response_model=TemplateResponse, status_code=201)
async def create_template(
    data: TemplateCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    template = DocumentTemplate(
        name=data.name,
        description=data.description,
        required_fields=data.required_fields,
        default_folder_id=data.default_folder_id,
        default_lifecycle_type=data.default_lifecycle_type,
        extraction_prompt=data.extraction_prompt,
    )
    db.add(template)
    await db.commit()
    await db.refresh(template)
    return template


@router.get("/api/templates", response_model=list[TemplateResponse])
async def list_templates(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(DocumentTemplate).order_by(DocumentTemplate.name))
    return list(result.scalars().all())


@router.get("/api/templates/{template_id}", response_model=TemplateResponse)
async def get_template(
    template_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    template = await db.get(DocumentTemplate, template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    return template


@router.put("/api/templates/{template_id}", response_model=TemplateResponse)
async def update_template(
    template_id: int,
    data: TemplateUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    template = await db.get(DocumentTemplate, template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    if data.name is not None:
        template.name = data.name
    if data.description is not None:
        template.description = data.description
    if data.required_fields is not None:
        template.required_fields = data.required_fields
    if data.default_folder_id is not None:
        template.default_folder_id = data.default_folder_id
    if data.default_lifecycle_type is not None:
        template.default_lifecycle_type = data.default_lifecycle_type
    if data.extraction_prompt is not None:
        template.extraction_prompt = data.extraction_prompt

    await db.commit()
    await db.refresh(template)
    return template


@router.delete("/api/templates/{template_id}", status_code=204)
async def delete_template(
    template_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    template = await db.get(DocumentTemplate, template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    await db.delete(template)
    await db.commit()


@router.post(
    "/api/templates/{template_id}/create-document",
    status_code=201,
)
async def create_document_from_template(
    template_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    template = await db.get(DocumentTemplate, template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    return {
        "template_id": template.id,
        "template_name": template.name,
        "required_fields": template.required_fields,
        "default_folder_id": template.default_folder_id,
        "default_lifecycle_type": template.default_lifecycle_type,
    }
