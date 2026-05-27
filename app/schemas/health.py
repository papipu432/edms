from datetime import datetime

from pydantic import BaseModel


class HealthIssue(BaseModel):
    issue_type: str
    severity: str
    document_id: int | None = None
    document_name: str | None = None
    detail: str
    recommended_action: str


class HealthReport(BaseModel):
    issues: list[HealthIssue]
    checked_at: datetime
    summary: dict[str, int]


class HealthDigest(BaseModel):
    report: HealthReport
    sent_to: list[str]
