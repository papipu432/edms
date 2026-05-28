from datetime import datetime

from pydantic import BaseModel


class ApprovalStepCreate(BaseModel):
    step_order: int
    approval_type: str  # "sequential" or "parallel"
    role_code: str | None = None
    user_id: str | None = None
    timeout_hours: int | None = None


class ApprovalChainCreate(BaseModel):
    name: str
    folder_id: int | None = None
    template_id: int | None = None
    steps: list[ApprovalStepCreate] = []


class ApprovalStepResponse(BaseModel):
    id: int
    chain_id: int
    step_order: int
    approval_type: str
    role_code: str | None = None
    user_id: str | None = None
    timeout_hours: int | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ApprovalChainResponse(BaseModel):
    id: int
    name: str
    folder_id: int | None = None
    template_id: int | None = None
    is_active: bool
    created_at: datetime
    steps: list[ApprovalStepResponse] = []

    model_config = {"from_attributes": True}


class ApprovalChainListResponse(BaseModel):
    id: int
    name: str
    folder_id: int | None = None
    template_id: int | None = None
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class ApprovalRequestCreate(BaseModel):
    document_id: int


class ApprovalRequestResponse(BaseModel):
    id: int
    document_id: int
    chain_id: int
    status: str
    current_step_order: int
    submitted_by: str
    submitted_at: datetime
    completed_at: datetime | None = None

    model_config = {"from_attributes": True}


class ApprovalDecisionCreate(BaseModel):
    decision: str  # "approved" or "rejected"
    comment: str | None = None


class ApprovalDecisionResponse(BaseModel):
    id: int
    request_id: int
    step_id: int
    user_id: str
    decision: str
    comment: str | None = None
    decided_at: datetime

    model_config = {"from_attributes": True}
