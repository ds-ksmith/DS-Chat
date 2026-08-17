import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class LinkPreview(Base):
    """A cache keyed by URL, not by message -- multiple messages (in the
    same room or different ones) linking the same URL share one fetch
    instead of each triggering their own. link_preview_service is the only
    writer; Message.preview_url (the first URL found in a message's
    content, set at creation time) is the join key a caller looks this up
    by."""

    __tablename__ = "link_previews"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    url: Mapped[str] = mapped_column(String(2048), unique=True, index=True, nullable=False)
    title: Mapped[str | None] = mapped_column(String(500))
    description: Mapped[str | None] = mapped_column(String(1000))
    image_url: Mapped[str | None] = mapped_column(String(2048))
    site_name: Mapped[str | None] = mapped_column(String(200))
    # Cached separately from a "no row yet" state so a URL that genuinely
    # doesn't unfurl (no title, fetch error, blocked by SSRF checks) isn't
    # re-fetched on every message that references it within the TTL.
    fetch_failed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp(), nullable=False
    )
