import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)


# Matches exactly the CSS custom properties frontend/src/styles/themes.css
# overrides per built-in preset -- a "custom" theme is applied the same way,
# just as inline styles on :root instead of a static stylesheet block (see
# frontend/src/lib/theme.ts). Hex-only (`#rrggbb`) since that's exactly what
# a native <input type="color"> always produces -- no alpha, no shorthand --
# so the pattern constraint can't reject anything the picker UI itself sends.
_HEX_COLOR = Field(pattern=r"^#[0-9a-fA-F]{6}$")


class CustomThemeColors(BaseModel):
    void: str = _HEX_COLOR
    void_2: str = _HEX_COLOR
    surface: str = _HEX_COLOR
    surface_2: str = _HEX_COLOR
    border: str = _HEX_COLOR
    text: str = _HEX_COLOR
    muted: str = _HEX_COLOR
    accent: str = _HEX_COLOR
    accent_2: str = _HEX_COLOR
    accent_3: str = _HEX_COLOR
    highlight: str = _HEX_COLOR
    danger: str = _HEX_COLOR
    color_scheme: Literal["light", "dark"]


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    email: EmailStr
    is_bot: bool
    is_site_admin: bool
    display_name: str | None
    theme: str | None
    custom_theme_colors: CustomThemeColors | None
    avatar_filename: str | None
    appear_offline: bool
    created_at: datetime


class ProfileUpdate(BaseModel):
    # Each field is independently optional-and-settable -- the router only
    # applies keys actually present in the request body
    # (model_dump(exclude_unset=True)), so a call that only wants to change
    # the theme doesn't clobber display_name (or appear_offline) back to
    # their defaults, and vice versa.
    display_name: str | None = Field(default=None, max_length=50)
    # Kept in sync with frontend/src/styles/themes.css's theme blocks.
    theme: Literal["dark", "light", "midnight", "sunset", "custom"] | None = Field(default=None)
    custom_theme_colors: CustomThemeColors | None = Field(default=None)
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
