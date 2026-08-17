import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

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
    password_confirm: str

    # Backend backstop -- the signup form does its own client-side match
    # check for immediate feedback (see SignupPage.tsx), but account
    # creation is irreversible enough (a typo'd password with no recovery
    # path until forgot-password) that the guarantee shouldn't rely on the
    # client alone.
    @model_validator(mode="after")
    def _passwords_match(self) -> "SignupComplete":
        if self.password != self.password_confirm:
            raise ValueError("Passwords don't match")
        return self
