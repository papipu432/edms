from datetime import datetime

from pydantic import BaseModel


class UserCreate(BaseModel):
    username: str
    email: str
    password: str


class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    is_active: bool
    roles: list[str] = []
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class RoleAssign(BaseModel):
    role_name: str


class FolderAssignmentCreate(BaseModel):
    folder_path: str
    role_name: str


class FolderAssignmentResponse(BaseModel):
    id: int
    user_id: int
    folder_path: str
    role_name: str
    granted_at: datetime

    model_config = {"from_attributes": True}


class LoginRequest(BaseModel):
    username: str
    password: str
