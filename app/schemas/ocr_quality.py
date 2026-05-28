from pydantic import BaseModel


class OCRQualityResponse(BaseModel):
    document_id: int
    ocr_confidence: float | None
    needs_review: bool
    page_confidences: list[float] | None = None
