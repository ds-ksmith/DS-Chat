import uuid

from pydantic import BaseModel


class MessageFileCreated(BaseModel):
    id: uuid.UUID
    filename: str
    size_bytes: int
    content_type: str
