import uuid
from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Message, MessageMention, MessageReaction
from app.schemas.message import ReactionSummary
from app.services.mention_service import extract_mentioned_user_ids


class MessageNotFoundError(Exception):
    pass


class NotMessageAuthorError(Exception):
    pass


async def create_message(
    db: AsyncSession,
    room_id: uuid.UUID,
    user_id: uuid.UUID,
    content: str | None = None,
    image_id: uuid.UUID | None = None,
    file_id: uuid.UUID | None = None,
) -> Message:
    message = Message(
        room_id=room_id, user_id=user_id, content=content, image_id=image_id, file_id=file_id
    )
    db.add(message)
    # message.id is available immediately (a Python-side uuid4 default, not
    # server-generated), so mention rows can reference it without a flush.
    if content:
        mentioned_ids = await extract_mentioned_user_ids(db, room_id, content)
        for mentioned_id in mentioned_ids:
            db.add(MessageMention(message_id=message.id, user_id=mentioned_id))
    await db.commit()
    await db.refresh(message)
    return message


async def edit_message(
    db: AsyncSession, message_id: uuid.UUID, editor_id: uuid.UUID, content: str
) -> Message:
    message = await db.get(Message, message_id)
    if message is None:
        raise MessageNotFoundError()
    if message.user_id != editor_id:
        raise NotMessageAuthorError()

    message.content = content
    message.edited_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(message)
    return message


async def list_recent_messages(
    db: AsyncSession, room_id: uuid.UUID, limit: int = 50
) -> list[Message]:
    result = await db.execute(
        select(Message)
        .where(Message.room_id == room_id)
        .options(selectinload(Message.user), selectinload(Message.file))
        .order_by(Message.created_at.desc())
        .limit(limit)
    )
    messages = list(result.scalars().all())
    messages.reverse()
    return messages


async def list_room_attachments(
    db: AsyncSession, room_id: uuid.UUID, limit: int = 100
) -> list[Message]:
    # Joins through messages.image_id/file_id rather than querying
    # message_files/message_images directly -- a file/image is uploaded (and
    # gets a row) *before* the message referencing it is ever sent, so an
    # upload the user abandoned without sending would otherwise show up as
    # a phantom attachment the room never actually saw.
    result = await db.execute(
        select(Message)
        .where(
            Message.room_id == room_id,
            or_(Message.image_id.isnot(None), Message.file_id.isnot(None)),
        )
        .options(selectinload(Message.user), selectinload(Message.file), selectinload(Message.image))
        .order_by(Message.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_reactions_for_messages(
    db: AsyncSession, message_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[ReactionSummary]]:
    if not message_ids:
        return {}

    result = await db.execute(
        select(MessageReaction)
        .where(MessageReaction.message_id.in_(message_ids))
        .order_by(MessageReaction.created_at)
    )
    # Grouped in Python rather than a GROUP BY/array_agg query -- the row
    # count per room-history page is small, and this keeps the ordering
    # (first-reacted emoji first, first-reacted user first within it)
    # trivial instead of relying on Postgres-specific aggregate ordering.
    by_message: dict[uuid.UUID, dict[str, list[str]]] = defaultdict(dict)
    for reaction in result.scalars().all():
        emoji_map = by_message[reaction.message_id]
        emoji_map.setdefault(reaction.emoji, []).append(str(reaction.user_id))

    return {
        message_id: [
            ReactionSummary(emoji=emoji, count=len(user_ids), user_ids=user_ids)
            for emoji, user_ids in emoji_map.items()
        ]
        for message_id, emoji_map in by_message.items()
    }


async def toggle_reaction(
    db: AsyncSession, message_id: uuid.UUID, user_id: uuid.UUID, emoji: str
) -> list[ReactionSummary]:
    result = await db.execute(
        select(MessageReaction).where(
            MessageReaction.message_id == message_id,
            MessageReaction.user_id == user_id,
            MessageReaction.emoji == emoji,
        )
    )
    existing = result.scalar_one_or_none()
    if existing is not None:
        await db.delete(existing)
    else:
        db.add(MessageReaction(message_id=message_id, user_id=user_id, emoji=emoji))
    await db.commit()

    reactions = await get_reactions_for_messages(db, [message_id])
    return reactions.get(message_id, [])
