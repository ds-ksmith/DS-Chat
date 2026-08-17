import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_bot: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_site_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(50))
    theme: Mapped[str | None] = mapped_column(String(20))
    # Only meaningful when theme == "custom" -- which of this user's saved
    # CustomTheme rows (app/models/custom_theme.py) is currently active.
    # Cleared explicitly (not via a DB-level ON DELETE) whenever that theme
    # is deleted -- see custom_theme_service.delete_custom_theme, which also
    # resets `theme` back to a preset in the same transaction so the two
    # columns can't go out of sync.
    active_custom_theme_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("custom_themes.id"), nullable=True
    )
    avatar_filename: Mapped[str | None] = mapped_column(String(64))
    avatar_content_type: Mapped[str | None] = mapped_column(String(50))
    # Manual override for the presence indicator -- when set, this user
    # always shows as offline to everyone regardless of actual connection
    # state (a "lurk" mode), independent of any individual room.
    appear_offline: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    active_custom_theme = relationship("CustomTheme", foreign_keys=[active_custom_theme_id])
