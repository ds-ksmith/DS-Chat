import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# Matches exactly the CSS custom properties frontend/src/styles/themes.css
# overrides per built-in preset -- a saved custom theme is applied the same
# way, just as inline styles on :root instead of a static stylesheet block
# (see frontend/src/lib/theme.ts). Hex-only (`#rrggbb`) since that's exactly
# what a native <input type="color"> always produces -- no alpha, no
# shorthand -- so the pattern constraint can't reject anything the picker UI
# itself sends.
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


class CustomThemeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    colors: CustomThemeColors


class CustomThemeUpdate(BaseModel):
    # Each field independently optional-and-settable, same convention as
    # ProfileUpdate -- a rename shouldn't require resending all 12 colors.
    name: str | None = Field(default=None, min_length=1, max_length=50)
    colors: CustomThemeColors | None = Field(default=None)


class CustomThemeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    colors: CustomThemeColors
    created_at: datetime
