import uuid

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class MessageMention(Base):
    __tablename__ = "message_mentions"

    message_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("messages.id"), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), primary_key=True, index=True
    )
