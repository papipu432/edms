from datetime import datetime

from pydantic import BaseModel


class ExpiryPrediction(BaseModel):
    document_id: int
    predicted_review_date: datetime | None = None
    confidence: float
    based_on_count: int
