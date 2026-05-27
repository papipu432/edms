from pydantic import BaseModel


class BulkUploadResult(BaseModel):
    document_id: int | None = None
    filename: str
    success: bool
    error: str | None = None

    model_config = {"from_attributes": True}


class BulkUploadResponse(BaseModel):
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
