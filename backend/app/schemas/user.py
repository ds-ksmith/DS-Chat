import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from app.schemas.custom_theme import CustomThemeRead


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    email: EmailStr
    is_bot: bool
    is_site_admin: bool
    display_name: str | None
    theme: str | None
    text_scale: str | None
    emoji_scale: str | None
    # Resolved, not just an id -- the frontend needs the actual palette to
    # paint on load without a second round trip (see lib/theme.ts).
    active_custom_theme: CustomThemeRead | None
    avatar_filename: str | None
    appear_offline: bool
    created_at: datetime

    @model_validator(mode="after")
    def _hide_custom_theme_when_not_active(self) -> "UserRead":
        # The DB deliberately keeps active_custom_theme_id set even while
        # theme is a preset (see custom_theme_service -- switching away from
        # custom must not lose the saved palette), so the ORM relationship
        # this field is populated from can be non-null even when the user
        # isn't actually on the custom theme right now. Enforce "only
        # meaningful when theme == 'custom'" here, in one place, rather than
        # relying on every router endpoint to remember it.
        if self.theme != "custom":
            self.active_custom_theme = None
        return self


class ProfileUpdate(BaseModel):
    # Each field is independently optional-and-settable -- the router only
    # applies keys actually present in the request body
    # (model_dump(exclude_unset=True)), so a call that only wants to change
    # the theme doesn't clobber display_name (or appear_offline) back to
    # their defaults, and vice versa.
    display_name: str | None = Field(default=None, max_length=50)
    # Kept in sync with frontend/src/styles/themes.css's theme blocks.
    # "custom" is deliberately not settable here -- becoming custom always
    # means activating one specific saved theme, which needs an id and an
    # ownership check; that's POST /api/custom-themes/{id}/activate, not a
    # bare theme name with nothing to point it at.
    theme: Literal["dark", "light", "midnight", "sunset"] | None = Field(default=None)
    # #71: kept in sync with frontend/src/lib/theme.ts's TEXT_SCALE_PERCENT map.
    text_scale: Literal["small", "normal", "large", "xlarge"] | None = Field(default=None)
    # #71: kept in sync with MessageContent.tsx's EMOJI_SCALE_MULTIPLIER map.
    emoji_scale: Literal["small", "normal", "large", "xlarge"] | None = Field(default=None)
    appear_offline: bool | None = Field(default=None)


class UserDirectoryRead(BaseModel):
    """Lightweight entry for user-picker UIs (room invites, admin ownership
    transfer) -- same visibility level as an avatar: any authenticated user
    can see this much about anyone (excludes bots, which aren't invited
    through these flows)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    display_name: str | None
    avatar_filename: str | None
