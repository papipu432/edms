from pydantic import BaseModel


class WikiPageResponse(BaseModel):
    path: str
    content: str


class WikiIndexResponse(BaseModel):
    content: str
    pages: list[str]


class WikiQueryRequest(BaseModel):
    question: str


class WikiQueryResponse(BaseModel):
    answer: str
    sources: list[str]


class LintIssue(BaseModel):
    type: str
    detail: str
    file: str | None = None


class WikiLintResponse(BaseModel):
    issues: list[LintIssue]


class WikiLogResponse(BaseModel):
    entries: list[str]
