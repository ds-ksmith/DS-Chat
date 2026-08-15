import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

DEFAULT_RESET_LIFETIME = timedelta(minutes=15)


def _default_expires_at() -> datetime:
    return datetime.now(timezone.utc) + DEFAULT_RESET_LIFETIME


class PasswordReset(Base):
    __tablename__ = "password_resets"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    # Same convention as SiteInvite.token_hash / API tokens: a bearer secret
    # looked up by itself, so it's hashed with security.hash_token (fast,
    # deterministic sha256), not argon2.
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_default_expires_at, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user = relationship("User")
