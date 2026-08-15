from pydantic import BaseModel, EmailStr, Field


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=200)


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordComplete(BaseModel):
    token: str
    new_password: str = Field(min_length=8, max_length=200)
