import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class CustomEmoji(Base):
    __tablename__ = "custom_emoji"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # #18: site-wide, not room-scoped -- kept globally unique so a bare
    # `:shortcode:` in any message/reaction is unambiguous without also
    # knowing which room it was posted in. 30 chars, not 32 -- the stored
    # *reference* in MessageReaction.emoji (String(32)) is the shortcode
    # wrapped in colons, so this is sized to leave room for both without
    # widening that column.
    shortcode: Mapped[str] = mapped_column(String(30), unique=True, index=True, nullable=False)
    storage_filename: Mapped[str] = mapped_column(String(64), nullable=False)
    content_type: Mapped[str] = mapped_column(String(50), nullable=False)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    uploader = relationship("User")
