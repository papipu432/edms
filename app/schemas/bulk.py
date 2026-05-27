from pydantic import BaseModel


class BulkUploadResult(BaseModel):
    document_id: int | None = None
    filename: str
    success: bool
    error: str | None = None

    model_config = {"from_attributes": True}


class BulkUploadResponse(BaseModel):
    """Response for bulk upload operations.

    Note: Bulk uploads use partial-commit semantics. If some files in a batch
    fail (e.g., due to validation errors), the successfully processed files are
    still committed and their processing pipelines are scheduled. The caller
    should inspect the per-file results to determine which files succeeded and
    which failed. A retry of the entire batch may produce duplicates for the
    files that already succeeded.
    """

    results: list[BulkUploadResult]
    total: int
    successful: int
    failed: int

    model_config = {"from_attributes": True}


class BulkActionRequest(BaseModel):
    document_ids: list[int]
    action: str
    comment: str | None = None


class BulkActionResult(BaseModel):
    document_id: int
    success: bool
    error: str | None = None

    model_config = {"from_attributes": True}


class BulkActionResponse(BaseModel):
    results: list[BulkActionResult]
    total: int
    successful: int
    failed: int

    model_config = {"from_attributes": True}
