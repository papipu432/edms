from fastapi import BackgroundTasks, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document, DocumentStatus
from app.models.group import Group
from app.models.workflow import WorkflowAction, WorkflowEntry
from app.schemas.bulk import (
    BulkActionResponse,
    BulkActionResult,
    BulkUploadResponse,
    BulkUploadResult,
)
from app.services.storage import StorageService


class BulkService:
    @staticmethod
    async def auto_create_folder_hierarchy(db: AsyncSession, folder_path: str) -> int:
        """Create nested Group hierarchy from a path like 'Finance/2024/Reports'.

        Returns the leaf group id. Idempotent - reuses existing groups.
        """
        segments = [s.strip() for s in folder_path.split("/") if s.strip()]
        if not segments:
            raise ValueError("folder_path must contain at least one segment")

        parent_id: int | None = None
        current_group_id: int = 0

        for segment in segments:
            result = await db.execute(
                select(Group).where(
                    Group.name == segment,
                    Group.parent_id == parent_id if parent_id is not None else Group.parent_id.is_(None),
                )
            )
            group = result.scalar_one_or_none()
            if group is None:
                group = Group(name=segment, parent_id=parent_id)
                db.add(group)
                await db.flush()
                await db.refresh(group)
            current_group_id = group.id
            parent_id = group.id

        return current_group_id

    @staticmethod
    async def bulk_upload(
        db: AsyncSession,
        files: list[UploadFile],
        storage_service: StorageService,
        background_tasks: BackgroundTasks,
        pipeline_db_url: str,
        group_id: int | None = None,
        folder_path: str | None = None,
    ) -> BulkUploadResponse:
        """Upload multiple files to a group, optionally creating folder hierarchy."""
        from app.api.documents import _run_pipeline

        # Determine target group
        if folder_path:
            group_id = await BulkService.auto_create_folder_hierarchy(db, folder_path)
        elif group_id is None:
            raise ValueError("Either group_id or folder_path must be provided")

        # Verify group exists
        group = await db.get(Group, group_id)
        if group is None:
            raise ValueError(f"Group {group_id} not found")

        results: list[BulkUploadResult] = []

        for file in files:
            filename = file.filename or "unnamed"
            try:
                file_content = await file.read()
                file_size = len(file_content)
                await file.seek(0)

                saved_path = await storage_service.save_upload(group_id, file, filename)

                content_type = file.content_type or "application/octet-stream"

                document = Document(
                    group_id=group_id,
                    original_filename=filename,
                    storage_path=str(saved_path),
                    file_type=content_type,
                    file_size=file_size,
                    status=DocumentStatus.processing,
                )
                db.add(document)
                await db.flush()
                await db.refresh(document)

                from app.tasks.document import process_document_task
                from app.tasks.utils import dispatch_task

                dispatch_task(
                    process_document_task,
                    background_tasks,
                    _run_pipeline,
                    document.id,
                    pipeline_db_url,
                )

                results.append(
                    BulkUploadResult(
                        document_id=document.id,
                        filename=filename,
                        success=True,
                    )
                )
            except Exception as e:
                results.append(
                    BulkUploadResult(
                        filename=filename,
                        success=False,
                        error=str(e),
                    )
                )

        successful = sum(1 for r in results if r.success)
        failed = sum(1 for r in results if not r.success)

        return BulkUploadResponse(
            results=results,
            total=len(results),
            successful=successful,
            failed=failed,
        )

    @staticmethod
    async def bulk_workflow_action(
        db: AsyncSession,
        document_ids: list[int],
        action: WorkflowAction,
        user_id: str,
        comment: str | None = None,
    ) -> BulkActionResponse:
        """Apply a workflow action to multiple documents."""
        results: list[BulkActionResult] = []

        for doc_id in document_ids:
            try:
                document = await db.get(Document, doc_id)
                if document is None:
                    results.append(
                        BulkActionResult(
                            document_id=doc_id,
                            success=False,
                            error="Document not found",
                        )
                    )
                    continue

                entry = WorkflowEntry(
                    document_id=doc_id,
                    user_id=user_id,
                    action=action,
                    comment=comment,
                )
                db.add(entry)
                await db.flush()

                results.append(
                    BulkActionResult(
                        document_id=doc_id,
                        success=True,
                    )
                )
            except Exception as e:
                results.append(
                    BulkActionResult(
                        document_id=doc_id,
                        success=False,
                        error=str(e),
                    )
                )

        successful = sum(1 for r in results if r.success)
        failed = sum(1 for r in results if not r.success)

        return BulkActionResponse(
            results=results,
            total=len(results),
            successful=successful,
            failed=failed,
        )
