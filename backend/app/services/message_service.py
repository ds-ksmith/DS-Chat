import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Message


async def create_message(
    db: AsyncSession, room_id: uuid.UUID, user_id: uuid.UUID, content: str
) -> Message:
    message = Message(room_id=room_id, user_id=user_id, content=content)
    db.add(message)
    await db.commit()
    await db.refresh(message)
    return message


async def list_recent_messages(
    db: AsyncSession, room_id: uuid.UUID, limit: int = 50
) -> list[Message]:
    result = await db.execute(
        select(Message)
        .where(Message.room_id == room_id)
        .order_by(Message.created_at.desc())
        .limit(limit)
    )
    messages = list(result.scalars().all())
    messages.reverse()
    return messages
