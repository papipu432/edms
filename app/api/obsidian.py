"""API endpoints for Obsidian vault export."""

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.core.config import settings
from app.services.obsidian_export import ObsidianExportService

router = APIRouter(prefix="/api/wiki/export/obsidian", tags=["obsidian"])

export_service = ObsidianExportService(wiki_path=settings.WIKI_PATH)


@router.get("")
async def export_obsidian_vault():
    """Export the full wiki as an Obsidian-compatible vault in a .zip file."""
    zip_buffer = export_service.create_vault_zip()

    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={
            "Content-Disposition": "attachment; filename=obsidian-vault.zip"
        },
    )


@router.get("/sync")
async def sync_obsidian_vault(
    since: str = Query(..., description="ISO 8601 timestamp for incremental sync"),
):
    """Return pages modified after the given timestamp for incremental sync."""
    try:
        changes = export_service.get_sync_changes(since_timestamp=since)
    except (ValueError, TypeError) as e:
        raise HTTPException(
            status_code=400, detail=f"Invalid timestamp format: {e}"
        )
    return changes


@router.get("/page/{page_path:path}")
async def get_obsidian_page(page_path: str):
    """Return a single wiki page in Obsidian format."""
    from app.services.wiki import WikiService

    wiki_service = WikiService(wiki_path=settings.WIKI_PATH)
    content = wiki_service.get_page(page_path)
    if content is None:
        raise HTTPException(status_code=404, detail="Wiki page not found")

    exported = export_service.export_page(page_path, content)
    return {"path": page_path, "content": exported}
