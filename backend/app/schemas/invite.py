import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models import InviteStatus


class InviteCreate(BaseModel):
    target_username: str = Field(min_length=1)


class InviteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    room_id: uuid.UUID
    invited_by: uuid.UUID
    target_user_id: uuid.UUID | None
    target_username: str | None = None
    status: InviteStatus
    expires_at: datetime
    created_at: datetime


class MyInviteRead(InviteRead):
    """InviteRead plus context the recipient can't otherwise resolve client-side --
    GET /api/invites/mine is for rooms the user isn't a member of yet."""

    room_name: str
    invited_by_username: str
