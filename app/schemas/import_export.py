from pydantic import BaseModel


class ImportResult(BaseModel):
    documents_created: int
    groups_created: int
    errors: list[str]


class ExportOptions(BaseModel):
    include_metadata: bool = True
    include_wiki: bool = True
