from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.document import Document
from app.models.group import Group
from app.models.user import User
from app.schemas.command_palette import CommandPaletteResponse, CommandPaletteResult

router = APIRouter(tags=["command_palette"])


@router.get("/api/command-palette/search", response_model=CommandPaletteResponse)
async def search_command_palette(
    q: str = Query("", description="Search query"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    results: list[CommandPaletteResult] = []

    if not q.strip():
        return CommandPaletteResponse(results=[])

    search_term = f"%{q}%"

    # Search documents
    doc_result = await db.execute(
        select(Document)
        .where(
            Document.original_filename.ilike(search_term)
            | Document.summary.ilike(search_term)
        )
        .limit(10)
    )
    for doc in doc_result.scalars().all():
        results.append(
            CommandPaletteResult(
                type="document",
                id=doc.id,
                title=doc.original_filename,
                url=f"/documents/{doc.id}",
                description=doc.summary[:100] if doc.summary else None,
            )
        )

    # Search groups
    group_result = await db.execute(
        select(Group).where(Group.name.ilike(search_term)).limit(10)
    )
    for group in group_result.scalars().all():
        results.append(
            CommandPaletteResult(
                type="group",
                id=group.id,
                title=group.name,
                url=f"/groups/{group.id}",
                description=group.description,
            )
        )

    return CommandPaletteResponse(results=results[:20])
