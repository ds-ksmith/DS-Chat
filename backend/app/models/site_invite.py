import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import DateTime, Enum, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.invite import InviteStatus

DEFAULT_SITE_INVITE_LIFETIME = timedelta(days=7)


def _default_expires_at() -> datetime:
    return datetime.now(timezone.utc) + DEFAULT_SITE_INVITE_LIFETIME


class SiteInvite(Base):
    """An admin-issued invite for someone with no account yet -- distinct
    from adding an existing user directly to a room."""

    __tablename__ = "site_invites"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    invited_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    # The raw token only ever exists in the invite email link -- like an API
    # token, it's a bearer secret looked up by itself, so it's stored hashed
    # (app.security.hash_token), not in plaintext.
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    status: Mapped[InviteStatus] = mapped_column(
        Enum(InviteStatus, name="invite_status"), default=InviteStatus.pending, nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_default_expires_at, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    inviter = relationship("User")
