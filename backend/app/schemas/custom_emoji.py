import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CustomEmojiRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    shortcode: str
    uploaded_by: uuid.UUID
    created_at: datetime
