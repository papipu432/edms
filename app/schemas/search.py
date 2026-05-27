from pydantic import BaseModel


class SearchRequest(BaseModel):
    query: str
    group_id: int | None = None
    top_k: int = 5


class SearchResult(BaseModel):
    chunk_text: str
    document_id: int
    document_name: str
    score: float


class SearchResponse(BaseModel):
    results: list[SearchResult]


class ChatSource(BaseModel):
    document_id: int
    document_name: str
    chunk_text: str


class ChatRequest(BaseModel):
    query: str
    group_id: int | None = None
    history: list[dict] | None = None


class ChatResponse(BaseModel):
    answer: str
    sources: list[ChatSource]
