from datetime import datetime

from pydantic import BaseModel


class VersionResponse(BaseModel):
    id: str
    document_id: int
    version_number: int
    file_size: int
    file_type: str
    uploader_id: str | None = None
    changelog: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class VersionListResponse(BaseModel):
    versions: list[VersionResponse]
    total: int


class VersionMetadata(BaseModel):
    version_number: int
    file_size: int
    file_type: str
    uploader_id: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class VersionCompareResponse(BaseModel):
    version_a: VersionMetadata
    version_b: VersionMetadata
    size_diff: int
    time_diff_seconds: float
