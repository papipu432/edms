from datetime import datetime

from pydantic import BaseModel


class ScheduledReportCreate(BaseModel):
    name: str
    schedule: str
    report_type: str
    recipients: list[str]
    filters: dict | None = None
    is_active: bool = True


class ScheduledReportUpdate(BaseModel):
    name: str | None = None
    schedule: str | None = None
    report_type: str | None = None
    recipients: list[str] | None = None
    filters: dict | None = None
    is_active: bool | None = None


class ScheduledReportResponse(BaseModel):
    id: int
    name: str
    schedule: str
    report_type: str
    recipients: list[str]
    filters: dict | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class ScheduledReportTriggerResponse(BaseModel):
    report_id: int
    status: str
    message: str
