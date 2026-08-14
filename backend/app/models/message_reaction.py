import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class MessageReaction(Base):
    __tablename__ = "message_reactions"
    __table_args__ = (
        UniqueConstraint(
            "message_id", "user_id", "emoji",
            name="uq_message_reactions_message_user_emoji",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    message_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("messages.id"), index=True, nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    emoji: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    message = relationship("Message")
    user = relationship("User")
