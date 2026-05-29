from datetime import datetime

from pydantic import BaseModel


class DocumentLifecycleCreate(BaseModel):
    lifecycle_type: str
    expires_at: datetime | None = None
    review_interval_days: int | None = None
    assigned_reviewer_id: str | None = None


class DocumentLifecycleResponse(BaseModel):
    id: int
    document_id: int
    lifecycle_type: str
    state: str
    expires_at: datetime | None = None
    review_interval_days: int | None = None
    next_review_at: datetime | None = None
    last_reviewed_at: datetime | None = None
    last_approved_at: datetime | None = None
    assigned_reviewer_id: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class LifecycleTransitionRequest(BaseModel):
    target_state: str
    comment: str | None = None


class LifecycleTransitionResponse(BaseModel):
    id: int
    lifecycle_id: int
    from_state: str
    to_state: str
    transitioned_by: str
    comment: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class LifecycleAlertItem(BaseModel):
    document_id: int
    document_name: str
    lifecycle_id: int
    alert_type: str
    days_remaining: int
    expires_at: datetime | None = None
    next_review_at: datetime | None = None


class LifecycleAlertsResponse(BaseModel):
    alerts: list[LifecycleAlertItem]
    total: int
