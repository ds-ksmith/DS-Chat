import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class WebhookIncomingCreate(BaseModel):
    description: str | None = Field(default=None, max_length=500)


class WebhookIncomingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    room_id: uuid.UUID
    token: str
    created_by: uuid.UUID
    description: str | None
    created_at: datetime


class WebhookIncomingAdminRead(WebhookIncomingRead):
    room_name: str
    created_by_username: str


class IncomingWebhookPost(BaseModel):
    content: str = Field(min_length=1)


class EventSubscriptionCreate(BaseModel):
    event_types: list[str] = Field(min_length=1)
    target_url: str = Field(min_length=1, max_length=2048)


class EventSubscriptionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    room_id: uuid.UUID | None
    event_types: list[str]
    target_url: str
    created_by: uuid.UUID
    created_at: datetime


class EventSubscriptionCreated(EventSubscriptionRead):
    signing_secret: str


class EventSubscriptionAdminRead(EventSubscriptionRead):
    room_name: str | None
    created_by_username: str
