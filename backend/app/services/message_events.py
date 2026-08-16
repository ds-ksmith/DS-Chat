import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Message, MessageFile, Room, RoomMembership, User
from app.schemas.message import ReactionSummary
from app.services.push_service import send_push_to_user
from app.services.webhook_service import dispatch_event
from app.ws.broadcaster import Broadcaster
from app.ws.presence import Presence


async def _notify_offline_members(
    db: AsyncSession, presence: Presence, room_id: uuid.UUID, sender: User, message: Message
) -> None:
    result = await db.execute(
        select(RoomMembership.user_id).where(RoomMembership.room_id == room_id)
    )
    member_ids = {row[0] for row in result.all()}
    # Subtract the sender explicitly rather than relying on them being
    # "connected" (true for the WS path, since they just sent this over an
    # active connection -- not true for the incoming-webhook REST path,
    # which has no WS connection for the attributed sender at all).
    offline_ids = member_ids - await presence.connected_user_ids(room_id) - {sender.id}
    if not offline_ids:
        return

    room = await db.get(Room, room_id)
    if message.content:
        body = f"{sender.username}: {message.content}"[:120]
    elif message.file_id:
        body = f"{sender.username} sent a file"
    else:
        body = f"{sender.username} sent an image"
    payload = {
        "title": f"#{room.name}" if room else "New message",
        "body": body,
        "room_id": str(room_id),
    }
    for user_id in offline_ids:
        await send_push_to_user(db, user_id, payload)


async def _message_payload(db: AsyncSession, message: Message, username: str) -> dict:
    file_payload = None
    if message.file_id:
        message_file = await db.get(MessageFile, message.file_id)
        if message_file:
            file_payload = {
                "id": str(message_file.id),
                "filename": message_file.original_filename,
                "size_bytes": message_file.size_bytes,
                "content_type": message_file.content_type,
            }
    return {
        "type": "message",
        "id": str(message.id),
        "room_id": str(message.room_id),
        "user_id": str(message.user_id),
        "username": username,
        "content": message.content,
        "image_id": str(message.image_id) if message.image_id else None,
        "file": file_payload,
        "reactions": [],
        "created_at": message.created_at.isoformat(),
        "edited_at": message.edited_at.isoformat() if message.edited_at else None,
    }


async def broadcast_new_message(
    db: AsyncSession,
    broadcaster: Broadcaster,
    presence: Presence,
    room_id: uuid.UUID,
    message: Message,
    sender: User,
) -> None:
    """The full side-effect sequence for a newly created message, shared by
    the WS "message" handler and the incoming-webhook receiver so both
    trigger identical fan-out/push/event behavior."""
    payload = await _message_payload(db, message, sender.username)
    await broadcaster.publish(room_id, payload)
    await _notify_offline_members(db, presence, room_id, sender, message)
    await dispatch_event(db, "message.created", room_id, payload)


async def broadcast_message_update(
    db: AsyncSession, broadcaster: Broadcaster, room_id: uuid.UUID, message: Message
) -> None:
    payload = {
        "type": "message_update",
        "id": str(message.id),
        "room_id": str(room_id),
        "content": message.content,
        "edited_at": message.edited_at.isoformat() if message.edited_at else None,
    }
    await broadcaster.publish(room_id, payload)
    await dispatch_event(db, "message.updated", room_id, payload)


async def broadcast_reaction_update(
    broadcaster: Broadcaster,
    room_id: uuid.UUID,
    message_id: uuid.UUID,
    reactions: list[ReactionSummary],
) -> None:
    payload = {
        "type": "reaction_update",
        "id": str(message_id),
        "room_id": str(room_id),
        "reactions": [r.model_dump() for r in reactions],
    }
    await broadcaster.publish(room_id, payload)
    # Deliberately no dispatch_event() call -- reactions don't get an
    # outgoing-webhook event type, matching the same scope cut made for
    # image uploads (see backend/README.md).


async def broadcast_room_added(broadcaster: Broadcaster, user_id: uuid.UUID, room: Room) -> None:
    """The only signal a user's open client gets that they were just added
    to a room -- without it, GET /rooms/mine is only ever fetched once at
    app mount, so a room added mid-session stays invisible until a full
    reload. Published on the user's own channel rather than the room's,
    since the whole point is reaching someone who hasn't joined that room's
    channel yet (and by definition can't have)."""
    await broadcaster.publish_to_user(
        user_id, {"type": "room_added", "room_id": str(room.id)}
    )
