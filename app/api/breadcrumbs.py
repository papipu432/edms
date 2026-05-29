from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.group import Group
from app.schemas.breadcrumb import BreadcrumbItem, BreadcrumbResponse

router = APIRouter(tags=["breadcrumbs"])


@router.get("/api/groups/{group_id}/breadcrumbs", response_model=BreadcrumbResponse)
async def get_group_breadcrumbs(
    group_id: int,
    db: AsyncSession = Depends(get_db),
):
    items: list[BreadcrumbItem] = []
    current_id: int | None = group_id

    # Walk up parent chain (max 20 levels to prevent infinite loops)
    visited: set[int] = set()
    while current_id is not None and len(visited) < 20:
        if current_id in visited:
            break
        visited.add(current_id)

        group = await db.get(Group, current_id)
        if not group:
            if not items:
                raise HTTPException(status_code=404, detail="Group not found")
            break
        items.append(
            BreadcrumbItem(
                id=group.id,
                name=group.name,
                url=f"/groups/{group.id}",
            )
        )
        current_id = group.parent_id

    # Reverse so root is first
    items.reverse()
    return BreadcrumbResponse(items=items)
