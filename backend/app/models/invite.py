import enum
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

DEFAULT_INVITE_LIFETIME = timedelta(days=7)


def _default_expires_at() -> datetime:
    return datetime.now(timezone.utc) + DEFAULT_INVITE_LIFETIME


class InviteStatus(str, enum.Enum):
    pending = "pending"
    accepted = "accepted"
    revoked = "revoked"


class RoomInvite(Base):
    __tablename__ = "room_invites"
    __table_args__ = (
        CheckConstraint(
            "target_user_id IS NOT NULL OR target_email IS NOT NULL",
            name="room_invites_target_required",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    room_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rooms.id"), index=True, nullable=False)
    invited_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    target_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), index=True)
    # Stored per the documented schema but not actionable yet: there's no
    # email-delivery mechanism anywhere in the stack. Phase 2 only creates
    # invites via target_user_id (existing users, looked up by username).
    target_email: Mapped[str | None] = mapped_column(String(255))
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_default_expires_at, nullable=False
    )
    status: Mapped[InviteStatus] = mapped_column(
        Enum(InviteStatus, name="invite_status"), default=InviteStatus.pending, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    room = relationship("Room")
    inviter = relationship("User", foreign_keys=[invited_by])
    target_user = relationship("User", foreign_keys=[target_user_id])
