import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, PrimaryKeyConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class RoomRole(str, enum.Enum):
    owner = "owner"
    admin = "admin"
    member = "member"


class RoomMembership(Base):
    __tablename__ = "room_memberships"
    __table_args__ = (PrimaryKeyConstraint("room_id", "user_id"),)

    room_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rooms.id"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    role: Mapped[RoomRole] = mapped_column(
        Enum(RoomRole, name="room_role"), default=RoomRole.member, nullable=False
    )
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # A server_default (not an app-code default) so every membership-creation
    # call site (create_room, join_room, add_member) gets a sane starting
    # point automatically: joining counts as being caught up as of then, not
    # retroactively unread for the room's entire prior history.
    last_read_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # #52 follow-up: lets a DM be hidden from one participant's own sidebar
    # without touching the other participant's copy or deleting anything --
    # a DM has no sensible "leave" (it would corrupt find_or_create_dm's
    # exactly-two-members assumption), so this is deliberately a per-viewer
    # display flag on their own membership row, not a membership deletion.
    # Cleared automatically (see message_events.py) whenever a new message
    # arrives in the room, or when find_or_create_dm resolves back to it --
    # both count as the conversation being active again.
    hidden_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    room = relationship("Room", back_populates="memberships")
    user = relationship("User")
