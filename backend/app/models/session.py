import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Session(Base):
    __tablename__ = "sessions"

    # #69: the row's own id doubles as the opaque value stored in the
    # signed session cookie (see app/dependencies.py) -- no separate
    # generate_token()/hash_token() pair like ApiToken needs. A bearer API
    # token has to be looked up *by itself* from a plaintext string a bot
    # pastes into an Authorization header (real leak risk, hence hashing
    # it at rest); this id only ever travels inside itsdangerous's signed,
    # tamper-proof cookie payload, so a plain UUID primary key carries the
    # same security properties the stateless cookie already had before
    # this table existed.
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    # 45 chars fits the longest possible IPv6 text representation.
    ip_address: Mapped[str | None] = mapped_column(String(45))
    user_agent: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # Bumped (throttled, not on every request -- see session_service.py) so
    # "active sessions" can be sorted/labeled by actual recent use, not just
    # login time -- a session opened once a week ago and used constantly
    # since should not look identical to one opened once and abandoned.
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # Null while active. Set on explicit logout or a deliberate "sign out
    # this device" from another session -- never deleted outright, so a
    # revoked row still means something if anyone ever needs to ask "was
    # this session valid at time X."
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user = relationship("User")
