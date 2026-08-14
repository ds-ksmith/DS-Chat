import uuid

from pydantic import BaseModel


class MessageImageCreated(BaseModel):
    id: uuid.UUID
