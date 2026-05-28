from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.document import Document
from app.models.smart_folder import SmartFolder
from app.models.user import User
from app.schemas.smart_folder import (
    SmartFolderCreate,
    SmartFolderResponse,
    SmartFolderResultsResponse,
    SmartFolderUpdate,
)

router = APIRouter(tags=["smart_folders"])


@router.post("/api/smart-folders", response_model=SmartFolderResponse, status_code=201)
async def create_smart_folder(
    data: SmartFolderCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    folder = SmartFolder(
        name=data.name,
        description=data.description,
        query_json=data.query_json,
        owner_id=current_user.id,
    )
    db.add(folder)
    await db.commit()
    await db.refresh(folder)
    return folder


@router.get("/api/smart-folders", response_model=list[SmartFolderResponse])
async def list_smart_folders(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(SmartFolder)
        .where(SmartFolder.owner_id == current_user.id)
        .order_by(SmartFolder.name)
    )
    return list(result.scalars().all())


@router.get("/api/smart-folders/{folder_id}", response_model=SmartFolderResponse)
async def get_smart_folder(
    folder_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    folder = await db.get(SmartFolder, folder_id)
    if not folder:
        raise HTTPException(status_code=404, detail="Smart folder not found")
    return folder


@router.put("/api/smart-folders/{folder_id}", response_model=SmartFolderResponse)
async def update_smart_folder(
    folder_id: int,
    data: SmartFolderUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    folder = await db.get(SmartFolder, folder_id)
    if not folder:
        raise HTTPException(status_code=404, detail="Smart folder not found")

    if data.name is not None:
        folder.name = data.name
    if data.description is not None:
        folder.description = data.description
    if data.query_json is not None:
        folder.query_json = data.query_json

    await db.commit()
    await db.refresh(folder)
    return folder


@router.delete("/api/smart-folders/{folder_id}", status_code=204)
async def delete_smart_folder(
    folder_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    folder = await db.get(SmartFolder, folder_id)
    if not folder:
        raise HTTPException(status_code=404, detail="Smart folder not found")
    await db.delete(folder)
    await db.commit()


@router.get(
    "/api/smart-folders/{folder_id}/documents",
    response_model=SmartFolderResultsResponse,
)
async def get_smart_folder_documents(
    folder_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    folder = await db.get(SmartFolder, folder_id)
    if not folder:
        raise HTTPException(status_code=404, detail="Smart folder not found")

    # Build query from query_json
    query = select(Document.id)
    if folder.query_json:
        if "group_id" in folder.query_json:
            query = query.where(Document.group_id == folder.query_json["group_id"])
        if "filename_contains" in folder.query_json:
            query = query.where(
                Document.original_filename.ilike(
                    f"%{folder.query_json['filename_contains']}%"
                )
            )
        if "status" in folder.query_json:
            query = query.where(Document.status == folder.query_json["status"])

    result = await db.execute(query)
    doc_ids = [row[0] for row in result.all()]

    return SmartFolderResultsResponse(
        folder=SmartFolderResponse.model_validate(folder),
        document_ids=doc_ids,
        total=len(doc_ids),
    )
