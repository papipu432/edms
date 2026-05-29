from pydantic import BaseModel

from app.schemas.search_enhanced import FacetedSearchResult


class NaturalSearchRequest(BaseModel):
    query: str


class NaturalSearchResponse(BaseModel):
    interpreted_query: dict
    results: list[FacetedSearchResult]
    raw_query: str
    parse_method: str
