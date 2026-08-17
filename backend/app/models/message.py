import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        CheckConstraint(
            "content IS NOT NULL OR image_id IS NOT NULL OR file_id IS NOT NULL",
            name="messages_content_or_attachment_required",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    room_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rooms.id"), index=True, nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    # Nullable since Phase "image uploads": a message can be an image with
    # no caption. The CheckConstraint above still requires at least one of
    # content/image_id/file_id.
    content: Mapped[str | None] = mapped_column(Text)
    image_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("message_images.id"))
    file_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("message_files.id"))
    # First http(s) URL found in content at creation time (see
    # link_preview_service.extract_first_url), if any -- a plain string, not
    # a FK, since the actual preview data lives in link_previews cached by
    # URL and is looked up separately (see message_service.list_recent_
    # messages), not eager-loaded as an ORM relationship.
    preview_url: Mapped[str | None] = mapped_column(String(2048))
    # clock_timestamp(), not now()/func.now() -- the WS handler (ws/chat.py)
    # shares one AsyncSession for a whole connection's lifetime, and a
    # read-only op (e.g. a "join" frame's membership check) can leave a
    # transaction open with nothing to commit it until the next write.
    # Postgres's now()/CURRENT_TIMESTAMP returns the *transaction's* start
    # time in that case, not the actual INSERT's -- confirmed live to be the
    # actual cause of #45 (a reply sent well after an idle read-only period
    # got timestamped to when that period started, sorting it before
    # messages that were genuinely sent earlier). clock_timestamp() always
    # reflects the real moment of execution regardless of transaction age.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp(), index=True, nullable=False
    )
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user = relationship("User")
    image = relationship("MessageImage")
    file = relationship("MessageFile")
