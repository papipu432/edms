from pydantic import BaseModel


class PreviewMetadata(BaseModel):
    document_id: int
    preview_type: str
    file_size: int
    exists: bool

    model_config = {"from_attributes": True}
