import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class MessageFile(Base):
    __tablename__ = "message_files"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    room_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rooms.id"), index=True, nullable=False)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    storage_filename: Mapped[str] = mapped_column(String(64), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    # Wider than MessageImage's content_type column -- generic MIME strings
    # (e.g. the Office Open XML types) run 60-80 chars, unlike images'
    # four known short values.
    content_type: Mapped[str] = mapped_column(String(150), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    room = relationship("Room")
    uploader = relationship("User")
