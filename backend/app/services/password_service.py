import secrets
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PasswordReset, User
from app.security import hash_password, hash_token, verify_password
from app.services.email_service import send_email


class InvalidCurrentPasswordError(Exception):
    pass


class PasswordResetInvalidError(Exception):
    pass


async def change_password(
    db: AsyncSession, user: User, current_password: str, new_password: str
) -> None:
    if not verify_password(current_password, user.password_hash):
        raise InvalidCurrentPasswordError()
    user.password_hash = hash_password(new_password)
    await db.commit()


async def request_password_reset(db: AsyncSession, email: str, base_url: str) -> None:
    # Always returns normally, whether or not the email matched an account --
    # the router never reveals which, to avoid leaking registered emails.
    result = await db.execute(
        select(User).where(User.email == email, User.is_active.is_(True))
    )
    user = result.scalar_one_or_none()
    if user is None:
        return

    raw_token = secrets.token_urlsafe(32)
    db.add(PasswordReset(user_id=user.id, token_hash=hash_token(raw_token)))
    await db.commit()

    reset_link = f"{base_url.rstrip('/')}/reset-password?token={raw_token}"
    await send_email(
        db,
        email,
        "Reset your DS Chat password",
        f"Someone requested a password reset for this account.\n\n"
        f"Reset it here:\n{reset_link}\n\n"
        f"This link expires in 15 minutes. If you didn't request this, "
        f"you can ignore this email.",
    )


async def _get_valid_reset(db: AsyncSession, token: str) -> PasswordReset:
    result = await db.execute(
        select(PasswordReset).where(PasswordReset.token_hash == hash_token(token))
    )
    reset = result.scalar_one_or_none()
    if reset is None or reset.used:
        raise PasswordResetInvalidError()
    if reset.expires_at <= datetime.now(timezone.utc):
        raise PasswordResetInvalidError()
    return reset


async def validate_reset_token(db: AsyncSession, token: str) -> None:
    await _get_valid_reset(db, token)


async def complete_password_reset(db: AsyncSession, token: str, new_password: str) -> User:
    reset = await _get_valid_reset(db, token)
    user = await db.get(User, reset.user_id)
    user.password_hash = hash_password(new_password)
    reset.used = True
    await db.commit()
    await db.refresh(user)
    return user
