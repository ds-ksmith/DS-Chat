import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Message


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
) -> Message:
    message = Message(room_id=room_id, user_id=user_id, content=content, image_id=image_id)
    db.add(message)
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
        .options(selectinload(Message.user))
        .order_by(Message.created_at.desc())
        .limit(limit)
    )
    messages = list(result.scalars().all())
    messages.reverse()
    return messages
