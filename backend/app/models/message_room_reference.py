import uuid

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class MessageRoomReference(Base):
    __tablename__ = "message_room_references"

    message_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("messages.id"), primary_key=True)
    room_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("rooms.id"), primary_key=True, index=True
    )
