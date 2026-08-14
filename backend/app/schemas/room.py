import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models import RoomRole


class RoomCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=2000)
    is_private: bool = False


class RoomUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=2000)


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


class RoomMemberRead(BaseModel):
    user_id: uuid.UUID
    username: str
    role: RoomRole
    joined_at: datetime


class RoomMemberRoleUpdate(BaseModel):
    role: RoomRole


class TransferOwnershipRequest(BaseModel):
    new_owner_user_id: uuid.UUID
