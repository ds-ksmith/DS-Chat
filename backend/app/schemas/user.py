import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    email: EmailStr
    is_bot: bool
    is_site_admin: bool
    display_name: str | None
    avatar_filename: str | None
    created_at: datetime


class ProfileUpdate(BaseModel):
    display_name: str | None = Field(default=None, max_length=50)


class UserDirectoryRead(BaseModel):
    """Lightweight entry for user-picker UIs (room invites, admin ownership
    transfer) -- same visibility level as an avatar: any authenticated user
    can see this much about anyone (excludes bots, which aren't invited
    through these flows)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    display_name: str | None
    avatar_filename: str | None
