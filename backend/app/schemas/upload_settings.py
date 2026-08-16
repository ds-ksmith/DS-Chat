from datetime import datetime

from pydantic import BaseModel, Field


class UploadSettingsRead(BaseModel):
    max_upload_bytes: int
    updated_at: datetime


class UploadSettingsUpdate(BaseModel):
    # Guardrails against a fat-fingered 0/negative value or an unbounded
    # figure that could exhaust disk -- 1 MB to 500 MB is generous enough
    # for any real attachment while still being a sane range to type into
    # a number input.
    max_upload_bytes: int = Field(ge=1024 * 1024, le=500 * 1024 * 1024)
