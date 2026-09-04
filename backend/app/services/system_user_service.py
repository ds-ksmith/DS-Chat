from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
from app.security import generate_token, hash_password

# #74: one well-known, auto-provisioned bot account the app itself posts as
# for automated first-party messages (the #72 welcome message, and whatever
# comes next) -- distinct from bot_service.py's admin-created integration
# bots, which each need a human actor and audit-log entry for creating them.
# There's no actor here: this account is provisioned lazily, the first time
# something needs to post as it.
SYSTEM_USERNAME = "system"


async def get_or_create_system_user(db: AsyncSession) -> User:
    result = await db.execute(select(User).where(User.username == SYSTEM_USERNAME))
    user = result.scalar_one_or_none()
    if user is not None:
        return user

    # Same placeholder-email/discarded-password shape as bot_service.create_bot
    # -- this account never logs in, email just satisfies the NOT NULL/unique
    # column.
    user = User(
        username=SYSTEM_USERNAME,
        email=f"{SYSTEM_USERNAME}@bots.example.com",
        password_hash=hash_password(generate_token()),
        is_bot=True,
    )
    db.add(user)
    try:
        await db.flush()
    except IntegrityError:
        # Two concurrent requests both found no existing row and raced to
        # create one -- the loser just reads back the winner's row instead
        # of erroring.
        await db.rollback()
        result = await db.execute(select(User).where(User.username == SYSTEM_USERNAME))
        return result.scalar_one()

    await db.commit()
    await db.refresh(user)
    return user
