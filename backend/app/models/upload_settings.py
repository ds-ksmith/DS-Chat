import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class UploadSettings(Base):
    """A single-row table (enforced in the service layer, not the schema --
    same convention as SmtpSettings) holding the site-wide max upload size
    for images and file attachments, set through the Admin UI."""

    __tablename__ = "upload_settings"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    max_upload_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
