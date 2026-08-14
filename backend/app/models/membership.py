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

    room = relationship("Room", back_populates="memberships")
    user = relationship("User")
