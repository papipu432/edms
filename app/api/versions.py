from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.version import VersionCompareResponse, VersionListResponse, VersionResponse
from app.services.audit import AuditService
from app.services.versioning import VersioningService

router = APIRouter(tags=["versions"])

versioning_service = VersioningService()
audit_service = AuditService()


@router.post(
    "/api/documents/{document_id}/versions",
    response_model=VersionResponse,
    status_code=201,
)
async def upload_version(
    document_id: int,
    request: Request,
    file: UploadFile,
    changelog: str | None = Form(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> VersionResponse:
    """Upload a new version of a document."""
    content = await file.read()
    file_size = len(content)
    filename = file.filename or "unknown"
    file_type = file.content_type or "application/octet-stream"

    try:
        version = await versioning_service.create_version(
            db=db,
            document_id=document_id,
            file_content=content,
            filename=filename,
            file_type=file_type,
            file_size=file_size,
            uploader_id=current_user.id,
            changelog=changelog,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    # Audit log
    await audit_service.log_action(
        db=db,
        document_id=document_id,
        action="version_create",
        actor=current_user,
        request=request,
        details={"version_number": version.version_number, "changelog": changelog},
    )

    await db.commit()
    return VersionResponse.model_validate(version)


@router.get(
    "/api/documents/{document_id}/versions",
    response_model=VersionListResponse,
)
async def list_versions(
    document_id: int,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """List all versions of a document."""
    versions = await versioning_service.list_versions(db=db, document_id=document_id)
    return {"versions": versions, "total": len(versions)}


@router.get(
    "/api/documents/{document_id}/versions/compare",
    response_model=VersionCompareResponse,
)
async def compare_versions(
    document_id: int,
    version_a: int = Query(..., description="Version number A"),
    version_b: int = Query(..., description="Version number B"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Compare metadata between two versions."""
    try:
        result = await versioning_service.compare_versions(
            db=db,
            document_id=document_id,
            version_a_num=version_a,
            version_b_num=version_b,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return result


@router.get(
    "/api/documents/{document_id}/versions/{version_id}",
    response_model=VersionResponse,
)
async def get_version(
    document_id: int,
    version_id: str,
    db: AsyncSession = Depends(get_db),
) -> VersionResponse:
    """Get metadata for a specific version."""
    version = await versioning_service.get_version(
        db=db, document_id=document_id, version_id=version_id
    )
    if version is None:
        raise HTTPException(status_code=404, detail="Version not found")
    return VersionResponse.model_validate(version)


@router.post(
    "/api/documents/{document_id}/versions/{version_id}/revert",
    response_model=VersionResponse,
)
async def revert_to_version(
    document_id: int,
    version_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> VersionResponse:
    """Revert a document to a specific version."""
    try:
        document = await versioning_service.revert_to_version(
            db=db, document_id=document_id, version_id=version_id
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    # Get the version we reverted to for the response
    version = await versioning_service.get_version(
        db=db, document_id=document_id, version_id=version_id
    )

    # Audit log
    await audit_service.log_action(
        db=db,
        document_id=document_id,
        action="revert",
        actor=current_user,
        request=request,
        details={"reverted_to_version": document.current_version},
    )

    await db.commit()
    return VersionResponse.model_validate(version)
