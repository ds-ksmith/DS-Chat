from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class SmtpSettingsUpdate(BaseModel):
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(ge=1, le=65535)
    username: str | None = None
    # None/omitted = keep the existing password unchanged -- the frontend
    # never has the plaintext to send back, only whether one is set.
    password: str | None = None
    from_address: EmailStr
    use_tls: bool = True


class SmtpSettingsRead(BaseModel):
    host: str
    port: int
    username: str | None
    has_password: bool
    from_address: str
    use_tls: bool
    updated_at: datetime
