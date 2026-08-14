import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        CheckConstraint(
            "content IS NOT NULL OR image_id IS NOT NULL",
            name="messages_content_or_image_required",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    room_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rooms.id"), index=True, nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    # Nullable since Phase "image uploads": a message can be an image with
    # no caption. The CheckConstraint above still requires at least one of
    # content/image_id.
    content: Mapped[str | None] = mapped_column(Text)
    image_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("message_images.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True, nullable=False
    )
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user = relationship("User")
    image = relationship("MessageImage")
