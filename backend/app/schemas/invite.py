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
    status: InviteStatus
    expires_at: datetime
    created_at: datetime
