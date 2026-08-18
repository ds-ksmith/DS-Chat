import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models import RoomRole


class RoomCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=2000)
    is_private: bool = False


class RoomUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=2000)
    is_private: bool | None = None


class RoomRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    is_private: bool
    owner_id: uuid.UUID
    created_at: datetime


class RoomListItem(RoomRead):
    is_member: bool


class MyRoomItem(RoomRead):
    role: RoomRole
    # Whether this room has a message newer than the caller's last_read_at --
    # computed by the router/service, not a stored column on Room itself
    # (it's inherently per-viewer, unlike everything else on RoomRead).
    has_unread: bool
    # Unread AND mentions this user specifically -- takes visual priority
    # over has_unread in the sidebar (see RoomRow.tsx), not shown alongside
    # it.
    has_mention: bool


class RoomMemberRead(BaseModel):
    user_id: uuid.UUID
    username: str
    display_name: str | None
    avatar_filename: str | None
    role: RoomRole
    joined_at: datetime
    # "offline" whenever the user has set appear_offline, regardless of
    # actual connection -- computed by the router (needs GlobalPresence),
    # not derivable from the model alone.
    status: Literal["online", "offline"]


class RoomMemberAdd(BaseModel):
    user_id: uuid.UUID


class RoomMemberRoleUpdate(BaseModel):
    role: RoomRole


class TransferOwnershipRequest(BaseModel):
    new_owner_user_id: uuid.UUID


class RoomAttachmentRead(BaseModel):
    id: uuid.UUID
    kind: Literal["file", "image"]
    # None for images -- MessageImage has no stored original filename,
    # unlike MessageFile (see backend/app/models/message_image.py).
    filename: str | None
    content_type: str
    size_bytes: int
    uploaded_by: str
    message_id: uuid.UUID
    created_at: datetime
