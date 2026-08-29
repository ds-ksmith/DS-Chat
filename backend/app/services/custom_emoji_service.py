import re
import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CustomEmoji, User
from app.storage import delete_file

# Deliberately stricter than the built-in Unicode shortcode set's charset
# (see frontend/src/lib/emojiShortcodes.ts, which also allows '+') -- this
# is validating a *new name being chosen*, not matching against an
# existing fixed list, so there's no reason to allow anything a person
# wouldn't naturally type. Max 30 chars matches CustomEmoji.shortcode's
# column width exactly (see that model's comment for why).
SHORTCODE_PATTERN = re.compile(r"^[a-z0-9_-]{2,30}$")


class InvalidShortcodeError(Exception):
    pass


class DuplicateShortcodeError(Exception):
    pass


class CustomEmojiNotFoundError(Exception):
    pass


class NotEmojiOwnerError(Exception):
    pass


async def create_custom_emoji(
    db: AsyncSession,
    uploaded_by: uuid.UUID,
    shortcode: str,
    storage_filename: str,
    content_type: str,
) -> CustomEmoji:
    if not SHORTCODE_PATTERN.match(shortcode):
        raise InvalidShortcodeError()

    emoji = CustomEmoji(
        shortcode=shortcode,
        storage_filename=storage_filename,
        content_type=content_type,
        uploaded_by=uploaded_by,
    )
    db.add(emoji)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise DuplicateShortcodeError() from exc
    await db.refresh(emoji)
    return emoji


async def list_custom_emoji(db: AsyncSession) -> list[CustomEmoji]:
    result = await db.execute(select(CustomEmoji).order_by(CustomEmoji.shortcode))
    return list(result.scalars().all())


async def get_custom_emoji_by_shortcode(db: AsyncSession, shortcode: str) -> CustomEmoji | None:
    result = await db.execute(select(CustomEmoji).where(CustomEmoji.shortcode == shortcode))
    return result.scalar_one_or_none()


async def delete_custom_emoji(db: AsyncSession, emoji_id: uuid.UUID, current_user: User) -> None:
    emoji = await db.get(CustomEmoji, emoji_id)
    if emoji is None:
        raise CustomEmojiNotFoundError()
    if emoji.uploaded_by != current_user.id and not current_user.is_site_admin:
        raise NotEmojiOwnerError()
    delete_file(emoji.storage_filename)
    await db.delete(emoji)
    await db.commit()
