import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ReactionSummary(BaseModel):
    emoji: str
    count: int
    user_ids: list[str]


class MessageFileInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    filename: str
    size_bytes: int
    content_type: str


class LinkPreviewInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    url: str
    title: str | None
    description: str | None
    image_url: str | None
    site_name: str | None
    is_image: bool


class MessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    room_id: uuid.UUID
    user_id: uuid.UUID
    username: str
    content: str | None
    image_id: uuid.UUID | None
    file: MessageFileInfo | None
    link_preview: LinkPreviewInfo | None
    reactions: list[ReactionSummary]
    created_at: datetime
    edited_at: datetime | None
    # #53: null for a live message; set once deleted, at which point
    # content/image_id/file/link_preview are all already cleared
    # server-side (see message_service.delete_message). `reactions` isn't
    # cleared server-side -- the frontend just doesn't render them once
    # deleted_at is set, same as it doesn't render the rest of a tombstone.
    deleted_at: datetime | None
