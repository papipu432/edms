from datetime import date, datetime

from pydantic import BaseModel


class HealthScoreComponent(BaseModel):
    name: str
    score: float
    detail: str


class HealthScoreResponse(BaseModel):
    composite_score: float
    components: list[HealthScoreComponent]
    computed_at: datetime


class HealthScoreHistoryItem(BaseModel):
    date: date
    composite_score: float
    orphan_score: float
    lifecycle_score: float
    backup_score: float
    security_score: float
    storage_score: float
    sla_score: float


class HealthScoreHistoryResponse(BaseModel):
    history: list[HealthScoreHistoryItem]
