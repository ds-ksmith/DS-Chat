import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class BotCreate(BaseModel):
    username: str = Field(min_length=3, max_length=50)


class BotRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    is_active: bool
    created_at: datetime


class ApiTokenCreate(BaseModel):
    scopes: list[str] = Field(min_length=1)


class ApiTokenRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    owner_id: uuid.UUID
    scopes: list[str]
    last_used_at: datetime | None
    created_at: datetime


class ApiTokenCreated(ApiTokenRead):
    token: str
