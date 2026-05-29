from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

import app.api.documents as doc_module
from app.api.workflow import _ACTION_ALLOWED_ROLES
from app.core.database import get_db
from app.core.security import get_current_user, role_required
from app.models.user import User
from app.models.workflow import WorkflowAction
from app.schemas.bulk import BulkActionRequest, BulkActionResponse, BulkUploadResponse
from app.services.bulk import BulkService

router = APIRouter(prefix="/api/bulk", tags=["bulk"])


class BulkShorthandRequest(BaseModel):
    document_ids: list[int]
    comment: str | None = None


@router.post("/upload", response_model=BulkUploadResponse)
async def bulk_upload(
    files: list[UploadFile],
    background_tasks: BackgroundTasks,
    group_id: int | None = None,
    folder_path: str | None = None,
    current_user: User = Depends(role_required(["editor", "admin"])),
    db: AsyncSession = Depends(get_db),
) -> BulkUploadResponse:
    """Upload multiple files at once to a group or folder path."""
    if group_id is None and folder_path is None:
        raise HTTPException(
            status_code=400,
            detail="Either group_id or folder_path must be provided",
        )

    try:
        return await BulkService.bulk_upload(
            db=db,
            files=files,
            storage_service=doc_module.storage_service,
            background_tasks=background_tasks,
            pipeline_db_url=doc_module.pipeline_db_url,
            group_id=group_id,
            folder_path=folder_path,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/workflow", response_model=BulkActionResponse)
async def bulk_workflow_action(
    data: BulkActionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BulkActionResponse:
    """Apply a workflow action to multiple documents."""
    # Validate action
    try:
        action = WorkflowAction(data.action)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid action: {data.action}",
        )

    # Check role permissions
    allowed_roles = _ACTION_ALLOWED_ROLES.get(action, [])
    user_roles = current_user.role_codes
    if not any(role in user_roles for role in allowed_roles):
        raise HTTPException(
            status_code=403,
            detail=f"Insufficient permissions for action '{action.value}'",
        )

    return await BulkService.bulk_workflow_action(
        db=db,
        document_ids=data.document_ids,
        action=action,
        user_id=current_user.id,
        comment=data.comment,
    )


@router.post("/approve", response_model=BulkActionResponse)
async def bulk_approve(
    data: BulkShorthandRequest,
    current_user: User = Depends(role_required(["approver", "admin"])),
    db: AsyncSession = Depends(get_db),
) -> BulkActionResponse:
    """Shorthand to approve multiple documents."""
    return await BulkService.bulk_workflow_action(
        db=db,
        document_ids=data.document_ids,
        action=WorkflowAction.approve,
        user_id=current_user.id,
        comment=data.comment,
    )


@router.post("/signoff", response_model=BulkActionResponse)
async def bulk_signoff(
    data: BulkShorthandRequest,
    current_user: User = Depends(role_required(["approver", "admin"])),
    db: AsyncSession = Depends(get_db),
) -> BulkActionResponse:
    """Shorthand to sign off multiple documents."""
    return await BulkService.bulk_workflow_action(
        db=db,
        document_ids=data.document_ids,
        action=WorkflowAction.sign_off,
        user_id=current_user.id,
        comment=data.comment,
    )
