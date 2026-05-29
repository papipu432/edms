from datetime import datetime

from pydantic import BaseModel


class ComplianceReportRequest(BaseModel):
    report_type: str
    start_date: str | None = None
    end_date: str | None = None
    format: str = "json"


class ComplianceReportResponse(BaseModel):
    id: int
    report_type: str
    generated_at: datetime
    data: dict
    export_url: str | None = None


class ComplianceReportListItem(BaseModel):
    id: int
    report_type: str
    generated_at: datetime
    format: str
