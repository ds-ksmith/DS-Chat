import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import ApiToken, User
from app.security import generate_token, hash_password, hash_token
from app.services.audit import record_audit_log

VALID_SCOPES = {"read:messages", "write:messages", "manage:rooms"}


class DuplicateBotError(Exception):
    pass


class BotNotFoundError(Exception):
    pass


class InvalidScopeError(Exception):
    pass


class TokenNotFoundError(Exception):
    pass


async def create_bot(db: AsyncSession, actor: User, username: str) -> User:
    # Bots never authenticate with a password -- generate one and discard
    # it. email is NOT NULL/unique today; a placeholder avoids widening the
    # schema just for accounts that will never receive real mail.
    # bots.example.com (not e.g. bots.local/.invalid) deliberately, since
    # pydantic's EmailStr rejects addresses whose *top-level* domain is one
    # of the IANA special-use TLDs (.local, .invalid, .test, ...) -- a
    # subdomain of the real (if reserved-for-docs) .com TLD isn't affected.
    bot = User(
        username=username,
        email=f"{username}@bots.example.com",
        password_hash=hash_password(generate_token()),
        is_bot=True,
    )
    db.add(bot)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise DuplicateBotError() from exc

    record_audit_log(db, actor, "bot.create", "user", bot.id)
    await db.commit()
    await db.refresh(bot)
    return bot


async def list_bots(db: AsyncSession) -> list[User]:
    result = await db.execute(
        select(User).where(User.is_bot.is_(True)).order_by(User.created_at)
    )
    return list(result.scalars().all())


async def _get_bot(db: AsyncSession, bot_id: uuid.UUID) -> User:
    bot = await db.get(User, bot_id)
    if bot is None or not bot.is_bot:
        raise BotNotFoundError()
    return bot


async def create_api_token(
    db: AsyncSession, actor: User, bot_id: uuid.UUID, scopes: list[str]
) -> tuple[ApiToken, str]:
    bot = await _get_bot(db, bot_id)
    if not set(scopes) <= VALID_SCOPES:
        raise InvalidScopeError()

    plaintext = generate_token()
    token = ApiToken(owner_id=bot.id, token_hash=hash_token(plaintext), scopes=scopes)
    db.add(token)
    record_audit_log(
        db, actor, "bot.issue_token", "user", bot.id, {"scopes": scopes}
    )
    await db.commit()
    await db.refresh(token)
    return token, plaintext


async def list_api_tokens(db: AsyncSession, bot_id: uuid.UUID) -> list[ApiToken]:
    result = await db.execute(
        select(ApiToken).where(ApiToken.owner_id == bot_id).order_by(ApiToken.created_at)
    )
    return list(result.scalars().all())


async def revoke_api_token(db: AsyncSession, actor: User, token_id: uuid.UUID) -> None:
    token = await db.get(ApiToken, token_id)
    if token is None:
        raise TokenNotFoundError()
    await db.delete(token)
    record_audit_log(db, actor, "bot.revoke_token", "user", token.owner_id)
    await db.commit()


async def resolve_token(db: AsyncSession, plaintext: str) -> tuple[User, ApiToken] | None:
    result = await db.execute(
        select(ApiToken)
        .where(ApiToken.token_hash == hash_token(plaintext))
        .options(selectinload(ApiToken.owner))
    )
    token = result.scalar_one_or_none()
    if token is None or not token.owner.is_active:
        return None

    token.last_used_at = datetime.now(timezone.utc)
    await db.commit()
    return token.owner, token
