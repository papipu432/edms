from typing import Any

from pydantic import BaseModel, Field


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


class ComparativeAnalysisRequest(BaseModel):
    document_ids: list[int] = Field(..., min_length=2, max_length=10)
    question: str


class ComparativeAnalysisResponse(BaseModel):
    analysis: str
    documents_analyzed: list[int]
    question: str
