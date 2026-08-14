import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ReactionSummary(BaseModel):
    emoji: str
    count: int
    user_ids: list[str]


class MessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    room_id: uuid.UUID
    user_id: uuid.UUID
    username: str
    content: str | None
    image_id: uuid.UUID | None
    reactions: list[ReactionSummary]
    created_at: datetime
    edited_at: datetime | None
