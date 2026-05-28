from datetime import datetime

from pydantic import BaseModel


class DelegationCreate(BaseModel):
    delegate_id: str
    start_date: datetime
    end_date: datetime
    scope_type: str = "all"
    scope_folder_id: int | None = None


class DelegationResponse(BaseModel):
    id: int
    delegator_id: str
    delegator_username: str | None = None
    delegate_id: str
    delegate_username: str | None = None
    start_date: datetime
    end_date: datetime
    scope_type: str
    scope_folder_id: int | None = None
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}
