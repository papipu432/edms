"""API endpoints for Canvas/Whiteboard feature."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.canvas import Canvas, CanvasConnection, CanvasItem
from app.models.user import User
from app.schemas.canvas import (
    CanvasConnectionCreate,
    CanvasConnectionResponse,
    CanvasConnectionUpdate,
    CanvasCreate,
    CanvasExport,
    CanvasExportEdge,
    CanvasExportNode,
    CanvasItemCreate,
    CanvasItemResponse,
    CanvasItemUpdate,
    CanvasResponse,
    CanvasUpdate,
)

router = APIRouter(prefix="/api/canvas", tags=["canvas"])


# --- Canvas CRUD ---


@router.post("", response_model=CanvasResponse)
async def create_canvas(
    data: CanvasCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CanvasResponse:
    """Create a new canvas."""
    canvas = Canvas(name=data.name, owner_id=current_user.id)
    db.add(canvas)
    await db.flush()
    await db.refresh(canvas)
    return CanvasResponse.model_validate(canvas)


@router.get("", response_model=list[CanvasResponse])
async def list_canvases(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[CanvasResponse]:
    """List all canvases for the current user."""
    result = await db.execute(
        select(Canvas).where(Canvas.owner_id == current_user.id)
    )
    canvases = result.scalars().all()
    return [CanvasResponse.model_validate(c) for c in canvases]


@router.get("/{canvas_id}", response_model=CanvasResponse)
async def get_canvas(
    canvas_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CanvasResponse:
    """Get a canvas by ID."""
    result = await db.execute(
        select(Canvas).where(Canvas.id == canvas_id, Canvas.owner_id == current_user.id)
    )
    canvas = result.scalar_one_or_none()
    if not canvas:
        raise HTTPException(status_code=404, detail="Canvas not found")
    return CanvasResponse.model_validate(canvas)


@router.put("/{canvas_id}", response_model=CanvasResponse)
async def update_canvas(
    canvas_id: int,
    data: CanvasUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CanvasResponse:
    """Update a canvas."""
    result = await db.execute(
        select(Canvas).where(Canvas.id == canvas_id, Canvas.owner_id == current_user.id)
    )
    canvas = result.scalar_one_or_none()
    if not canvas:
        raise HTTPException(status_code=404, detail="Canvas not found")
    if data.name is not None:
        canvas.name = data.name
    await db.flush()
    await db.refresh(canvas)
    return CanvasResponse.model_validate(canvas)


@router.delete("/{canvas_id}")
async def delete_canvas(
    canvas_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Delete a canvas."""
    result = await db.execute(
        select(Canvas).where(Canvas.id == canvas_id, Canvas.owner_id == current_user.id)
    )
    canvas = result.scalar_one_or_none()
    if not canvas:
        raise HTTPException(status_code=404, detail="Canvas not found")
    await db.delete(canvas)
    await db.flush()
    return {"detail": "Canvas deleted"}


# --- CanvasItem CRUD ---


@router.post("/{canvas_id}/items", response_model=CanvasItemResponse)
async def create_canvas_item(
    canvas_id: int,
    data: CanvasItemCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CanvasItemResponse:
    """Add an item to a canvas."""
    result = await db.execute(
        select(Canvas).where(Canvas.id == canvas_id, Canvas.owner_id == current_user.id)
    )
    canvas = result.scalar_one_or_none()
    if not canvas:
        raise HTTPException(status_code=404, detail="Canvas not found")

    item = CanvasItem(
        canvas_id=canvas_id,
        document_id=data.document_id,
        note_text=data.note_text,
        x_position=data.x_position,
        y_position=data.y_position,
        width=data.width,
        height=data.height,
        color=data.color,
    )
    db.add(item)
    await db.flush()
    await db.refresh(item)
    return CanvasItemResponse.model_validate(item)


@router.get("/{canvas_id}/items", response_model=list[CanvasItemResponse])
async def list_canvas_items(
    canvas_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[CanvasItemResponse]:
    """List all items in a canvas."""
    result = await db.execute(
        select(CanvasItem).where(CanvasItem.canvas_id == canvas_id)
    )
    items = result.scalars().all()
    return [CanvasItemResponse.model_validate(i) for i in items]


@router.put("/{canvas_id}/items/{item_id}", response_model=CanvasItemResponse)
async def update_canvas_item(
    canvas_id: int,
    item_id: int,
    data: CanvasItemUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CanvasItemResponse:
    """Update a canvas item."""
    result = await db.execute(
        select(CanvasItem).where(
            CanvasItem.id == item_id, CanvasItem.canvas_id == canvas_id
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Canvas item not found")

    for field in ["document_id", "note_text", "x_position", "y_position", "width", "height", "color"]:
        value = getattr(data, field)
        if value is not None:
            setattr(item, field, value)

    await db.flush()
    await db.refresh(item)
    return CanvasItemResponse.model_validate(item)


@router.delete("/{canvas_id}/items/{item_id}")
async def delete_canvas_item(
    canvas_id: int,
    item_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Delete a canvas item."""
    result = await db.execute(
        select(CanvasItem).where(
            CanvasItem.id == item_id, CanvasItem.canvas_id == canvas_id
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Canvas item not found")
    await db.delete(item)
    await db.flush()
    return {"detail": "Canvas item deleted"}


# --- CanvasConnection CRUD ---


@router.post("/{canvas_id}/connections", response_model=CanvasConnectionResponse)
async def create_canvas_connection(
    canvas_id: int,
    data: CanvasConnectionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CanvasConnectionResponse:
    """Add a connection between two items in a canvas."""
    result = await db.execute(
        select(Canvas).where(Canvas.id == canvas_id, Canvas.owner_id == current_user.id)
    )
    canvas = result.scalar_one_or_none()
    if not canvas:
        raise HTTPException(status_code=404, detail="Canvas not found")

    conn = CanvasConnection(
        canvas_id=canvas_id,
        from_item_id=data.from_item_id,
        to_item_id=data.to_item_id,
        label=data.label,
    )
    db.add(conn)
    await db.flush()
    await db.refresh(conn)
    return CanvasConnectionResponse.model_validate(conn)


@router.get("/{canvas_id}/connections", response_model=list[CanvasConnectionResponse])
async def list_canvas_connections(
    canvas_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[CanvasConnectionResponse]:
    """List all connections in a canvas."""
    result = await db.execute(
        select(CanvasConnection).where(CanvasConnection.canvas_id == canvas_id)
    )
    connections = result.scalars().all()
    return [CanvasConnectionResponse.model_validate(c) for c in connections]


@router.delete("/{canvas_id}/connections/{connection_id}")
async def delete_canvas_connection(
    canvas_id: int,
    connection_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Delete a canvas connection."""
    result = await db.execute(
        select(CanvasConnection).where(
            CanvasConnection.id == connection_id,
            CanvasConnection.canvas_id == canvas_id,
        )
    )
    conn = result.scalar_one_or_none()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")
    await db.delete(conn)
    await db.flush()
    return {"detail": "Connection deleted"}


# --- Export ---


@router.get("/{canvas_id}/export", response_model=CanvasExport)
async def export_canvas(
    canvas_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CanvasExport:
    """Export a canvas in Obsidian .canvas format."""
    result = await db.execute(
        select(Canvas).where(Canvas.id == canvas_id, Canvas.owner_id == current_user.id)
    )
    canvas = result.scalar_one_or_none()
    if not canvas:
        raise HTTPException(status_code=404, detail="Canvas not found")

    # Get items
    items_result = await db.execute(
        select(CanvasItem).where(CanvasItem.canvas_id == canvas_id)
    )
    items = items_result.scalars().all()

    # Get connections
    conns_result = await db.execute(
        select(CanvasConnection).where(CanvasConnection.canvas_id == canvas_id)
    )
    connections = conns_result.scalars().all()

    # Build export nodes
    export_nodes = []
    for item in items:
        node_type = "text" if item.note_text else "file"
        text = item.note_text or f"Document #{item.document_id}"
        export_nodes.append(
            CanvasExportNode(
                id=str(item.id),
                x=item.x_position,
                y=item.y_position,
                width=item.width,
                height=item.height,
                type=node_type,
                text=text,
                color=item.color,
            )
        )

    # Build export edges
    export_edges = []
    for conn in connections:
        export_edges.append(
            CanvasExportEdge(
                id=str(conn.id),
                fromNode=str(conn.from_item_id),
                toNode=str(conn.to_item_id),
                label=conn.label,
            )
        )

    return CanvasExport(nodes=export_nodes, edges=export_edges)
