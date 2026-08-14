import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class AdminUserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    email: EmailStr
    is_bot: bool
    is_site_admin: bool
    is_active: bool
    created_at: datetime


class AdminRoomRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    is_private: bool
    is_archived: bool
    owner_id: uuid.UUID
    created_at: datetime
    member_count: int


class AuditLogEntryRead(BaseModel):
    id: uuid.UUID
    actor_id: uuid.UUID
    actor_username: str
    action: str
    target_type: str
    target_id: uuid.UUID
    metadata: dict | None
    created_at: datetime


class ResetPasswordRequest(BaseModel):
    new_password: str = Field(min_length=8, max_length=200)


class TransferOwnershipRequest(BaseModel):
    new_owner_id: uuid.UUID
