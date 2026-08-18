import re
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Room, RoomMembership
from app.services.mention_service import strip_code_spans

ROOM_REFERENCE_PATTERN = re.compile(r"#([a-zA-Z0-9_.-]+)")


async def extract_referenced_room_ids(
    db: AsyncSession, sender_id: uuid.UUID, content: str
) -> set[uuid.UUID]:
    """Resolves `#roomname` tokens in `content` against rooms the *sender*
    is a member of -- deliberately not the room the message is being sent
    in (the whole point is referencing a *different* room), and not open to
    arbitrary site rooms either (#47: referencing a private room the sender
    isn't in would leak its existence to anyone reading the message, even
    though they aren't in it either)."""
    room_names = set(ROOM_REFERENCE_PATTERN.findall(strip_code_spans(content)))
    if not room_names:
        return set()

    result = await db.execute(
        select(Room.id)
        .join(RoomMembership, RoomMembership.room_id == Room.id)
        .where(RoomMembership.user_id == sender_id, Room.name.in_(room_names))
    )
    return {row[0] for row in result.all()}
