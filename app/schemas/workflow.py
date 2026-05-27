from datetime import datetime

from pydantic import BaseModel


class WorkflowActionRequest(BaseModel):
    comment: str | None = None


class WorkflowEntryResponse(BaseModel):
    id: int
    document_id: int
    user_id: str
    action: str
    comment: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
