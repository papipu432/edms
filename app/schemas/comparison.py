from typing import Any

from pydantic import BaseModel


class MetadataField(BaseModel):
    field: str
    doc_a_value: Any = None
    doc_b_value: Any = None
    differs: bool


class MetadataComparisonResponse(BaseModel):
    fields: list[MetadataField]


class ContentDiffResponse(BaseModel):
    unified_diff: str
    additions_count: int
    deletions_count: int
    similarity_ratio: float


class ComparisonResponse(BaseModel):
    metadata: MetadataComparisonResponse | None = None
    content_diff: ContentDiffResponse | None = None
    has_content_diff: bool = False
