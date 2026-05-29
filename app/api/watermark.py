"""Watermark API router for managing watermark configurations and applying watermarks."""

import io

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.document import Document
from app.models.user import User
from app.models.watermark import WatermarkConfig
from app.schemas.watermark import (
    WatermarkConfigCreate,
    WatermarkConfigResponse,
    WatermarkConfigUpdate,
)
from app.services.watermark import WatermarkService

router = APIRouter(tags=["watermark"])

watermark_service = WatermarkService()


async def _require_admin(user: User) -> None:
    """Check that the current user has admin role."""
    if "admin" not in user.role_codes:
        raise HTTPException(status_code=403, detail="Admin role required")


@router.get("/api/watermark/configs", response_model=list[WatermarkConfigResponse])
async def list_watermark_configs(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List watermark configurations (admin only)."""
    await _require_admin(current_user)

    result = await db.execute(select(WatermarkConfig))
    configs = result.scalars().all()

    return [
        WatermarkConfigResponse(
            id=c.id,
            group_id=c.group_id,
            text_template=c.text_template,
            opacity=c.opacity,
            position=c.position,
            enabled=c.enabled,
            created_at=c.created_at,
        )
        for c in configs
    ]


@router.post("/api/watermark/configs", response_model=WatermarkConfigResponse)
async def create_watermark_config(
    config_data: WatermarkConfigCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new watermark configuration (admin only)."""
    await _require_admin(current_user)

    if config_data.position not in ("diagonal", "top", "bottom", "center"):
        raise HTTPException(
            status_code=400,
            detail="Position must be one of: diagonal, top, bottom, center",
        )

    config = WatermarkConfig(
        group_id=config_data.group_id,
        text_template=config_data.text_template,
        opacity=config_data.opacity,
        position=config_data.position,
    )
    db.add(config)
    await db.flush()
    await db.refresh(config)

    return WatermarkConfigResponse(
        id=config.id,
        group_id=config.group_id,
        text_template=config.text_template,
        opacity=config.opacity,
        position=config.position,
        enabled=config.enabled,
        created_at=config.created_at,
    )


@router.put("/api/watermark/configs/{config_id}", response_model=WatermarkConfigResponse)
async def update_watermark_config(
    config_id: int,
    config_data: WatermarkConfigUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update a watermark configuration (admin only)."""
    await _require_admin(current_user)

    result = await db.execute(
        select(WatermarkConfig).where(WatermarkConfig.id == config_id)
    )
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="Config not found")

    if config_data.text_template is not None:
        config.text_template = config_data.text_template
    if config_data.opacity is not None:
        config.opacity = config_data.opacity
    if config_data.position is not None:
        if config_data.position not in ("diagonal", "top", "bottom", "center"):
            raise HTTPException(
                status_code=400,
                detail="Position must be one of: diagonal, top, bottom, center",
            )
        config.position = config_data.position
    if config_data.enabled is not None:
        config.enabled = config_data.enabled

    await db.flush()
    await db.refresh(config)

    return WatermarkConfigResponse(
        id=config.id,
        group_id=config.group_id,
        text_template=config.text_template,
        opacity=config.opacity,
        position=config.position,
        enabled=config.enabled,
        created_at=config.created_at,
    )


@router.delete("/api/watermark/configs/{config_id}")
async def delete_watermark_config(
    config_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a watermark configuration (admin only)."""
    await _require_admin(current_user)

    result = await db.execute(
        select(WatermarkConfig).where(WatermarkConfig.id == config_id)
    )
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="Config not found")

    await db.delete(config)
    return {"detail": "Config deleted"}


@router.post("/api/documents/{document_id}/watermarked")
async def download_watermarked_document(
    document_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Download a watermarked copy of a document (authenticated user)."""
    # Get the document
    result = await db.execute(
        select(Document).where(Document.id == document_id)
    )
    document = result.scalar_one_or_none()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    # Get watermark config for the document's group
    config = await watermark_service.get_config_for_group(db, document.group_id)
    if not config:
        raise HTTPException(
            status_code=404, detail="No watermark configuration found"
        )

    # Render watermark text
    text = watermark_service.render_text(
        config.text_template,
        user=current_user.username,
        doc_id=str(document.id),
    )

    # Read the document file
    import os

    file_path = document.storage_path
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Document file not found")

    with open(file_path, "rb") as f:
        file_bytes = f.read()

    # Apply watermark based on file type
    file_type = document.file_type.lower()

    if file_type in ("application/pdf", "pdf"):
        watermarked = watermark_service.apply_pdf_watermark(
            file_bytes, text, config.opacity, config.position
        )
        media_type = "application/pdf"
        filename = f"watermarked_{document.original_filename}"
    elif file_type in ("image/png", "image/jpeg", "image/jpg", "png", "jpeg", "jpg"):
        watermarked = watermark_service.apply_image_watermark(
            file_bytes, text, config.opacity, config.position
        )
        media_type = "image/png"
        filename = f"watermarked_{document.original_filename}"
    else:
        # For other file types, return CSS watermark as HTML
        css_watermark = watermark_service.generate_css_watermark(
            text, config.opacity, config.position
        )
        html_content = f"<html><body>{css_watermark}<p>Watermarked document preview not available for this file type.</p></body></html>"
        return Response(
            content=html_content,
            media_type="text/html",
            headers={
                "Content-Disposition": f'inline; filename="watermarked_{document.original_filename}.html"'
            },
        )

    return Response(
        content=watermarked,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        },
    )
