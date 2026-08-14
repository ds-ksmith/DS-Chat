import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class SmtpSettings(Base):
    """A single-row table (enforced in the service layer, not the schema --
    there's no clean single-row DB constraint) holding the site's SMTP
    configuration, set through the Admin UI at runtime rather than the env
    file."""

    __tablename__ = "smtp_settings"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    host: Mapped[str] = mapped_column(String(255), nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False)
    username: Mapped[str | None] = mapped_column(String(255))
    # Encrypted at rest (app.crypto) with a key derived from SESSION_SECRET
    # -- the only reversible secret this app stores in the database, unlike
    # password_hash (one-way) or api_tokens (looked up by hash, never
    # decrypted).
    password_encrypted: Mapped[str | None] = mapped_column(Text)
    from_address: Mapped[str] = mapped_column(String(255), nullable=False)
    use_tls: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
