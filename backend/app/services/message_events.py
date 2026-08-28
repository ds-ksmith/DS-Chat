import asyncio
import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Message, MessageFile, MessageMention, Room, RoomMembership, User
from app.schemas.message import ReactionSummary
from app.services.link_preview_service import fetch_and_broadcast_link_preview
from app.services.push_service import send_push_to_user
from app.services.room_service import list_dm_partner_ids
from app.services.webhook_service import dispatch_event
from app.ws.broadcaster import Broadcaster
from app.ws.focus_presence import FocusPresence
from app.ws.presence import Presence


async def _notify_offline_members(
    db: AsyncSession,
    broadcaster: Broadcaster,
    presence: Presence,
    focus_presence: FocusPresence,
    room_id: uuid.UUID,
    sender: User,
    message: Message,
) -> None:
    result = await db.execute(
        select(RoomMembership.user_id).where(RoomMembership.room_id == room_id)
    )
    member_ids = {row[0] for row in result.all()}
    connected_ids = await presence.connected_user_ids(room_id)
    # Subtract the sender explicitly rather than relying on them being
    # "connected" (true for the WS path, since they just sent this over an
    # active connection -- not true for the incoming-webhook REST path,
    # which has no WS connection for the attributed sender at all).
    offline_ids = member_ids - connected_ids - {sender.id}

    # #59: a desktop-mode member can be *connected* to this room's channel
    # (it's open on screen, live messages are rendering) while their window
    # sits unfocused behind something else -- still exactly the situation a
    # desktop notification should fire for, same as #49's original intent.
    # This used to be handled by the client faking "offline" (leaving the
    # room's channel on blur), which also silently stopped live delivery to
    # that room; FocusPresence is a separate signal so notification
    # eligibility no longer has to ride on room-connection state at all.
    connected_but_unfocused_ids = {
        user_id
        for user_id in connected_ids - {sender.id}
        if await focus_presence.is_unfocused(user_id)
    }
    notify_ids = offline_ids | connected_but_unfocused_ids
    if not notify_ids:
        return

    result = await db.execute(
        select(MessageMention.user_id).where(MessageMention.message_id == message.id)
    )
    mentioned_ids = {row[0] for row in result.all()}

    # Unread-dot audience stays exactly offline_ids, not notify_ids: a
    # connected-but-unfocused member still has the room open and rendering
    # on screen right now, so it isn't actually "unread" for them the way a
    # room they haven't got open at all is.
    for user_id in offline_ids:
        await broadcaster.publish_to_user(
            user_id,
            {
                "type": "unread_update",
                "room_id": str(room_id),
                "mentioned": user_id in mentioned_ids,
            },
        )

    room = await db.get(Room, room_id)
    title = f"#{room.name}" if room else "New message"
    for user_id in notify_ids:
        mentioned = user_id in mentioned_ids
        if message.content:
            prefix = f"{sender.username} mentioned you: " if mentioned else f"{sender.username}: "
            body = (prefix + message.content)[:120]
        elif message.file_id:
            body = f"{sender.username} sent a file"
        else:
            body = f"{sender.username} sent an image"
        payload = {"title": title, "body": body, "room_id": str(room_id)}
        await send_push_to_user(db, user_id, payload)
        # Desktop notifications (#49): delivered over this same already-open
        # authenticated socket rather than Web Push, since Electron has no
        # push delivery service configured. Broadcast to every eligible
        # offline member regardless of push-subscription status -- the
        # client decides whether to act on it (only when window.dsDesktop
        # is present), so the server doesn't need to track which clients
        # are running inside Electron. `id` is the message's own id
        # (stable, not random) so the client can dedupe across socket
        # reconnects/replays, the same way Electron's own eventId dedup
        # does on its side.
        await broadcaster.publish_to_user(
            user_id,
            {
                "type": "desktop_notification",
                "id": str(message.id),
                "room_id": str(room_id),
                "title": title,
                "body": body,
            },
        )


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
        # Never populated here -- fetching it is a network call to a
        # third-party URL, which has no business delaying message delivery.
        # A separate "link_preview" envelope arrives shortly after (see
        # _maybe_fetch_link_preview) once/if the fetch succeeds.
        "link_preview": None,
        "reactions": [],
        "created_at": message.created_at.isoformat(),
        "edited_at": message.edited_at.isoformat() if message.edited_at else None,
    }


def _maybe_fetch_link_preview(broadcaster: Broadcaster, room_id: uuid.UUID, message: Message) -> None:
    if message.preview_url:
        asyncio.create_task(
            fetch_and_broadcast_link_preview(broadcaster, room_id, message.id, message.preview_url)
        )


async def broadcast_new_message(
    db: AsyncSession,
    broadcaster: Broadcaster,
    presence: Presence,
    focus_presence: FocusPresence,
    room_id: uuid.UUID,
    message: Message,
    sender: User,
) -> None:
    """The full side-effect sequence for a newly created message, shared by
    the WS "message" handler and the incoming-webhook receiver so both
    trigger identical fan-out/push/event behavior."""
    payload = await _message_payload(db, message, sender.username)
    await broadcaster.publish(room_id, payload)
    # A no-op for a regular room (hidden_at is only ever set on a DM's
    # membership row -- see RoomMembership.hidden_at) -- new activity
    # un-hiding a DM someone closed matches find_or_create_dm's own
    # un-hide-on-reopen behavior. `.returning` so we know exactly who was
    # un-hidden -- their client needs the same room_added signal a brand
    # new DM does (see broadcast_room_added's docstring): the room wasn't
    # in their already-loaded room list at all, so unread_update's plain
    # setRooms(prev => prev.map(...)) can't make it reappear -- there's
    # nothing in `prev` for it to match.
    unhidden_result = await db.execute(
        update(RoomMembership)
        .where(RoomMembership.room_id == room_id, RoomMembership.hidden_at.is_not(None))
        .values(hidden_at=None)
        .returning(RoomMembership.user_id)
    )
    unhidden_user_ids = list(unhidden_result.scalars().all())
    await db.commit()
    for unhidden_user_id in unhidden_user_ids:
        await broadcaster.publish_to_user(
            unhidden_user_id, {"type": "room_added", "room_id": str(room_id)}
        )
    await _notify_offline_members(db, broadcaster, presence, focus_presence, room_id, sender, message)
    await dispatch_event(db, "message.created", room_id, payload)
    _maybe_fetch_link_preview(broadcaster, room_id, message)


async def broadcast_message_update(
    db: AsyncSession, broadcaster: Broadcaster, room_id: uuid.UUID, message: Message
) -> None:
    payload = {
        "type": "message_update",
        "id": str(message.id),
        "room_id": str(room_id),
        "content": message.content,
        "edited_at": message.edited_at.isoformat() if message.edited_at else None,
        # Lets the frontend clear a stale preview when an edit changes or
        # removes the URL it came from -- it compares this against the
        # link_preview it already has for the message rather than blindly
        # keeping whatever was there before the edit.
        "preview_url": message.preview_url,
    }
    await broadcaster.publish(room_id, payload)
    await dispatch_event(db, "message.updated", room_id, payload)
    _maybe_fetch_link_preview(broadcaster, room_id, message)


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


async def broadcast_member_updated(db: AsyncSession, broadcaster: Broadcaster, user_id: uuid.UUID) -> None:
    """Tells every room a user belongs to that their displayable info
    (avatar, display name) changed -- without it, other members' already-
    fetched member lists (and anything resolving avatar/name from them,
    like MessageList) go stale until the room is reopened. Only reaches
    clients that currently have that room's channel joined, which is
    exactly when a stale avatar would actually be visible on screen."""
    result = await db.execute(
        select(RoomMembership.room_id).where(RoomMembership.user_id == user_id)
    )
    for (room_id,) in result.all():
        await broadcaster.publish(
            room_id, {"type": "member_updated", "room_id": str(room_id), "user_id": str(user_id)}
        )


async def broadcast_dm_presence_update(
    db: AsyncSession, broadcaster: Broadcaster, user_id: uuid.UUID, online: bool
) -> None:
    """Tells every one of user_id's DM partners that their online/offline
    status just changed (#63) -- on each partner's own per-user channel,
    not the DM room's channel. The room channel alone doesn't reach the
    sidebar: Presence gates room-channel delivery on actually having that
    specific room's channel joined right now, which is only ever the one
    room currently open in the UI -- so a DM sitting unopened in the
    sidebar (which is the normal case; the sidebar shows every DM's status
    at once) never saw its partner's status change until something else
    forced a full room-list refetch."""
    for partner_id in await list_dm_partner_ids(db, user_id):
        await broadcaster.publish_to_user(
            partner_id,
            {
                "type": "dm_presence_update",
                "user_id": str(user_id),
                "status": "online" if online else "offline",
            },
        )


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
