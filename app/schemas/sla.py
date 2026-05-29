from datetime import datetime

from pydantic import BaseModel


class SLAPolicyCreate(BaseModel):
    folder_id: int | None = None
    template_id: int | None = None
    action: str = "approval"
    max_duration_hours: int
    escalation_role: str | None = None


class SLAPolicyResponse(BaseModel):
    id: int
    folder_id: int | None = None
    template_id: int | None = None
    action: str
    max_duration_hours: int
    escalation_role: str | None = None
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class DocumentSLAResponse(BaseModel):
    id: int
    document_id: int
    policy_id: int
    started_at: datetime
    deadline_at: datetime
    status: str
    completed_at: datetime | None = None
    escalated: bool
    percent_elapsed: float = 0.0

    model_config = {"from_attributes": True}


class SLADashboardResponse(BaseModel):
    total: int
    on_time: int
    at_risk: int
    breached: int
    completed: int
    compliance_rate: float
