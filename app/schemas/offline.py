from pydantic import BaseModel


class OfflineRequest(BaseModel):
    document_ids: list[int] | None = None
    group_id: int | None = None


class OfflineStatus(BaseModel):
    status: str
    message: str
