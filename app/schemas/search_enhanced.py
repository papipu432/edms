from datetime import datetime

from pydantic import BaseModel, Field


class FacetedSearchRequest(BaseModel):
    query: str | None = None
    group_id: int | None = None
    lifecycle_state: str | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
    keywords: list[str] | None = None
    file_type: str | None = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


class FacetedSearchResult(BaseModel):
    document_id: int
    document_name: str
    group_id: int
    file_type: str
    created_at: datetime
    score: float | None = None


class FacetedSearchResponse(BaseModel):
    results: list[FacetedSearchResult]
    facets: dict
    total_count: int
    page: int
    page_size: int


class SearchSuggestion(BaseModel):
    text: str
    source: str


class SuggestionsResponse(BaseModel):
    suggestions: list[SearchSuggestion]


class RelatedDocument(BaseModel):
    document_id: int
    document_name: str
    similarity_score: float


class RelatedDocumentsResponse(BaseModel):
    document_id: int
    related: list[RelatedDocument]


class SearchHistoryItem(BaseModel):
    id: int
    query_text: str
    filters_json: dict | None = None
    results_count: int
    searched_at: datetime


class SearchHistoryResponse(BaseModel):
    history: list[SearchHistoryItem]
