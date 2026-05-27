from datetime import datetime

from pydantic import BaseModel


class AnnotationCreate(BaseModel):
    text: str
    start_offset: int | None = None
    end_offset: int | None = None


class AnnotationResponse(BaseModel):
    id: int
    document_id: int
    user_id: int
    text: str
    start_offset: int | None = None
    end_offset: int | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
