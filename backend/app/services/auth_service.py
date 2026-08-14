from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
from app.schemas.user import UserCreate
from app.security import hash_password, verify_password


class DuplicateUserError(Exception):
    pass


class InvalidCredentialsError(Exception):
    pass


class AccountDeactivatedError(Exception):
    pass


async def register_user(db: AsyncSession, data: UserCreate) -> User:
    user = User(
        username=data.username,
        email=data.email,
        password_hash=hash_password(data.password),
    )
    db.add(user)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise DuplicateUserError() from exc

    await db.refresh(user)
    return user


async def authenticate_user(
    db: AsyncSession, username_or_email: str, password: str
) -> User:
    result = await db.execute(
        select(User).where(
            or_(User.username == username_or_email, User.email == username_or_email)
        )
    )
    user = result.scalar_one_or_none()
    if user is None or not verify_password(password, user.password_hash):
        raise InvalidCredentialsError()
    if not user.is_active:
        raise AccountDeactivatedError()
    return user
