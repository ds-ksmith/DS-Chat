import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models import InviteStatus


class SiteInviteCreate(BaseModel):
    email: EmailStr


class SiteInviteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    invited_by: uuid.UUID
    status: InviteStatus
    expires_at: datetime
    created_at: datetime


class SignupValidateRead(BaseModel):
    email: str


class SignupComplete(BaseModel):
    token: str
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=8, max_length=200)
