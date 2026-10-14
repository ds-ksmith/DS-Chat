import asyncio
import contextlib
import logging
import time
import uuid

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import ApiToken, Message, MessageFile, MessageImage, Room, RoomMembership, User
from app.services.bot_service import resolve_token
from app.services.message_events import (
    broadcast_dm_presence_update,
    broadcast_member_updated,
    broadcast_message_delete,
    broadcast_message_update,
    broadcast_new_message,
    broadcast_reaction_update,
)
from app.services.message_service import (
    MessageNotFoundError,
    NotMessageAuthorError,
    create_message,
    delete_message,
    edit_message,
    toggle_reaction,
)
from app.services.room_service import mark_room_read
from app.services.session_service import resolve_session

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ws"])

WS_UNAUTHENTICATED = 4401

# #76: comfortably under the ~60s idle-connection timeout common to reverse
# proxies/load balancers sitting in front of this endpoint, and short enough
# that the frontend's own zombie-detection watchdog (useChatSocket.ts) can
# notice a dead connection and reconnect well within a session -- a socket
# can go silently dead (no close frame at all, e.g. a laptop sleeping or a
# NAT dropping an idle mapping) without this, and no live message reaches it
# again until *something* else finally triggers a close, which used to be
# "switch rooms and back" purely by accident (that remounts the message
# list, which refetches history over plain REST -- unrelated to the socket
# itself actually recovering).
WS_PING_INTERVAL_SECONDS = 30

# #77: a human client that has sent nothing -- not even the "pong" to the ping
# above -- for this long is treated as gone and disconnected, so its presence
# stops being renewed and cleanup runs. Needed on top of the transport's own
# keepalive: a browser answers *protocol-level* pings from its network layer
# even while the page's JavaScript is frozen (a suspended or discarded tab,
# a sleeping laptop that keeps its network up), so the connection looks
# healthy forever while nobody is actually there. Only the page itself can
# send the app-level "pong". The frontend reconnects on any non-4401 close.
WS_DEAD_AFTER_SECONDS = 90
WS_HEARTBEAT_TIMEOUT = 4408

# Presence entries (see ExpiringPresenceSet) are renewed on incoming frames,
# at most this often -- a chatty client shouldn't turn every message into
# several extra Redis writes.
PRESENCE_REFRESH_MIN_INTERVAL_SECONDS = 10


class ClientEnvelope(BaseModel):
    type: str
    room_id: uuid.UUID | None = None
    content: str | None = None
    image_id: uuid.UUID | None = None
    file_id: uuid.UUID | None = None
    message_id: uuid.UUID | None = None
    emoji: str | None = None
    focused: bool | None = None


async def _is_room_member(db: AsyncSession, room_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    result = await db.execute(
        select(RoomMembership).where(
            RoomMembership.room_id == room_id, RoomMembership.user_id == user_id
        )
    )
    return result.scalar_one_or_none() is not None


async def _is_room_archived(db: AsyncSession, room_id: uuid.UUID) -> bool:
    room = await db.get(Room, room_id)
    return room is not None and room.is_archived


def _missing_scope(api_token: ApiToken | None, scope: str) -> bool:
    return api_token is not None and scope not in api_token.scopes


async def _broadcast_offline(db: AsyncSession, broadcaster, user_id: uuid.UUID) -> None:
    await broadcast_member_updated(db, broadcaster, user_id)
    await broadcast_dm_presence_update(db, broadcaster, user_id, online=False)


async def _best_effort(label: str, awaitable):
    # Disconnect cleanup is several independent Redis/DB steps; one failing
    # must not skip the ones after it.
    try:
        return await awaitable
    except Exception:
        logger.warning("Presence cleanup step failed: %s", label, exc_info=True)
        return None


@router.websocket("/ws/chat")
async def chat_endpoint(websocket: WebSocket, db: AsyncSession = Depends(get_db)) -> None:
    api_token: ApiToken | None = None

    # Bots authenticate by setting Authorization on the WS handshake itself
    # (not a browser cookie) -- same connection type/endpoint a human client
    # uses, just a different credential.
    auth_header = websocket.headers.get("authorization")
    if auth_header and auth_header.lower().startswith("bearer "):
        resolved = await resolve_token(db, auth_header[len("bearer ") :].strip())
        if resolved is None:
            await websocket.close(code=WS_UNAUTHENTICATED)
            return
        user, api_token = resolved
    else:
        session_id_raw = websocket.session.get("session_id")
        if not session_id_raw:
            await websocket.close(code=WS_UNAUTHENTICATED)
            return
        session = await resolve_session(db, uuid.UUID(session_id_raw))
        if session is None:
            await websocket.close(code=WS_UNAUTHENTICATED)
            return
        user = await db.get(User, session.user_id)
        if user is None or not user.is_active:
            await websocket.close(code=WS_UNAUTHENTICATED)
            return

    await websocket.accept()
    manager = websocket.app.state.connection_manager
    presence = websocket.app.state.presence
    global_presence = websocket.app.state.global_presence
    focus_presence = websocket.app.state.focus_presence
    broadcaster = websocket.app.state.broadcaster
    joined_rooms: set[uuid.UUID] = set()
    # Tracks this connection's last-reported focus state (see the "focus"
    # envelope below) so the disconnect cleanup can release FocusPresence's
    # refcount if the socket closes while still blurred -- mirroring how
    # joined_rooms tracks per-connection room membership for its own cleanup.
    is_blurred = False
    # Identifies this connection's own presence entries (#77) -- see
    # ExpiringPresenceSet -- so one connection ending can't affect another
    # belonging to the same user, and a dead one can simply stop renewing.
    conn_id = uuid.uuid4().hex
    last_frame_at = time.monotonic()
    last_presence_refresh = last_frame_at
    manager.register_user(user.id, websocket)
    # Only broadcast on a genuine offline->online transition (this user's
    # first open connection), not for every extra tab -- broadcast_member_
    # updated tells every room this user's in to refresh, which would be
    # wasted churn on a transition that didn't actually change anything
    # visible.
    if await global_presence.connect(user.id, conn_id):
        await broadcast_member_updated(db, broadcaster, user.id)
        await broadcast_dm_presence_update(db, broadcaster, user.id, online=True)
    # This session is shared for the connection's entire lifetime (which can
    # be hours) -- SQLAlchemy opens a transaction implicitly on first use,
    # and every read above (the auth lookup, broadcast_member_updated's own
    # query) leaves it open with nothing to ever close it otherwise. Left
    # uncommitted, that transaction sits "idle in transaction" holding locks
    # for as long as the socket stays open -- confirmed in production
    # blocking unrelated schema migrations on the same tables for 30+
    # minutes. Committing here, and again after every frame below, means
    # the connection is never sitting on an open transaction while merely
    # waiting for the next one.
    await db.commit()

    async def refresh_presence() -> None:
        # Renews every presence entry this connection holds. If the global
        # one had already lapsed (a long stall) this is also the moment the
        # user comes back online, and has to be announced like a fresh connect.
        if await global_presence.refresh(user.id, conn_id):
            await broadcast_member_updated(db, broadcaster, user.id)
            await broadcast_dm_presence_update(db, broadcaster, user.id, online=True)
        for room_id in joined_rooms:
            await presence.refresh(room_id, user.id, conn_id)
        if is_blurred:
            await focus_presence.refresh(user.id, conn_id)

    try:
        while True:
            try:
                raw = await asyncio.wait_for(
                    websocket.receive_json(), timeout=WS_PING_INTERVAL_SECONDS
                )
            except asyncio.TimeoutError:
                # Nothing received in a while -- ping rather than assume the
                # connection's still good. A genuinely dead socket fails this
                # send (raising, caught below same as any other disconnect);
                # a merely quiet one just gets proded and the loop continues
                # waiting.
                if api_token is None and time.monotonic() - last_frame_at >= WS_DEAD_AFTER_SECONDS:
                    # Gone (see WS_DEAD_AFTER_SECONDS). The socket may be too
                    # dead to even take a close frame; either way, leaving the
                    # loop runs the normal cleanup below.
                    with contextlib.suppress(Exception):
                        await websocket.close(code=WS_HEARTBEAT_TIMEOUT)
                    break
                if api_token is not None:
                    # A bot isn't expected to speak our app-level heartbeat
                    # (it may just ignore the ping), so it can't be dropped
                    # for not answering and its presence can't depend on
                    # answers. While the handler is alive the transport's own
                    # keepalive is what vouches for it -- a dead bot socket
                    # ends this handler, and cleanup does the rest.
                    await refresh_presence()
                    last_presence_refresh = time.monotonic()
                    await db.commit()
                await websocket.send_json({"type": "ping"})
                continue
            last_frame_at = time.monotonic()
            try:
                if last_frame_at - last_presence_refresh >= PRESENCE_REFRESH_MIN_INTERVAL_SECONDS:
                    await refresh_presence()
                    last_presence_refresh = last_frame_at
                try:
                    envelope = ClientEnvelope.model_validate(raw)
                except ValidationError:
                    await websocket.send_json({"type": "error", "detail": "Malformed message"})
                    continue

                if envelope.type == "join":
                    if envelope.room_id is None:
                        await websocket.send_json({"type": "error", "detail": "room_id required"})
                        continue
                    if not await _is_room_member(db, envelope.room_id, user.id):
                        await websocket.send_json(
                            {"type": "error", "detail": "Not a member of this room"}
                        )
                        continue
                    manager.join(envelope.room_id, websocket)
                    await presence.join(envelope.room_id, user.id, conn_id)
                    joined_rooms.add(envelope.room_id)
                    await websocket.send_json({"type": "joined", "room_id": str(envelope.room_id)})

                elif envelope.type == "pong":
                    # #76: the client's reply to our "ping" above -- nothing
                    # to do with it. Its only purpose is resetting the
                    # frontend's own liveness watchdog; the timeout on the
                    # receive_json() above already gets reset by receiving
                    # any frame at all, this one included.
                    pass

                elif envelope.type == "leave":
                    if envelope.room_id is None:
                        await websocket.send_json({"type": "error", "detail": "room_id required"})
                        continue
                    manager.leave(envelope.room_id, websocket)
                    await presence.leave(envelope.room_id, user.id, conn_id)
                    joined_rooms.discard(envelope.room_id)

                elif envelope.type == "focus":
                    # Sent only by the desktop client (#59), independent of
                    # room join/leave -- see FocusPresence's docstring for
                    # why widening desktop_notification eligibility this
                    # way no longer needs to touch live room delivery at
                    # all, unlike the "leave the room's channel on blur"
                    # approach this replaced.
                    if envelope.focused is None:
                        await websocket.send_json({"type": "error", "detail": "focused required"})
                        continue
                    if envelope.focused:
                        if is_blurred:
                            await focus_presence.mark_focused(user.id, conn_id)
                            is_blurred = False
                    else:
                        if not is_blurred:
                            await focus_presence.mark_blurred(user.id, conn_id)
                            is_blurred = True

                elif envelope.type == "message":
                    if envelope.room_id is None or (
                        not envelope.content
                        and envelope.image_id is None
                        and envelope.file_id is None
                    ):
                        await websocket.send_json(
                            {
                                "type": "error",
                                "detail": "room_id and content or image_id or file_id required",
                            }
                        )
                        continue
                    if _missing_scope(api_token, "write:messages"):
                        await websocket.send_json(
                            {"type": "error", "detail": "Token missing required scope: write:messages"}
                        )
                        continue
                    if envelope.room_id not in joined_rooms or not await _is_room_member(
                        db, envelope.room_id, user.id
                    ):
                        await websocket.send_json(
                            {"type": "error", "detail": "Not a member of this room"}
                        )
                        continue
                    if await _is_room_archived(db, envelope.room_id):
                        # #57: history stays fully readable (joining/reading
                        # an archived room's channel is untouched above),
                        # this is the one gate that actually makes archiving
                        # do something for people who were already members.
                        await websocket.send_json(
                            {"type": "error", "detail": "This room has been archived and is read-only"}
                        )
                        continue
                    image_id = None
                    if envelope.image_id is not None:
                        image = await db.get(MessageImage, envelope.image_id)
                        if image is None or image.room_id != envelope.room_id:
                            await websocket.send_json({"type": "error", "detail": "Invalid image"})
                            continue
                        image_id = image.id
                    file_id = None
                    if envelope.file_id is not None:
                        message_file = await db.get(MessageFile, envelope.file_id)
                        if message_file is None or message_file.room_id != envelope.room_id:
                            await websocket.send_json({"type": "error", "detail": "Invalid file"})
                            continue
                        file_id = message_file.id
                    message = await create_message(
                        db, envelope.room_id, user.id, envelope.content, image_id, file_id
                    )
                    # Sending implies having seen the room as of now --
                    # without this, GET /rooms/mine would show the sender's
                    # own room as unread the instant they send into it
                    # (last_read_at isn't otherwise bumped until the
                    # frontend's own message echo triggers a mark-read
                    # call, which is a real but avoidable race).
                    # Deliberately not done in create_message() itself: the
                    # incoming-webhook path also calls it, and a webhook's
                    # attributed sender may not actually be watching.
                    await mark_room_read(db, envelope.room_id, user.id)
                    await broadcast_new_message(
                        db,
                        broadcaster,
                        presence,
                        focus_presence,
                        global_presence,
                        str(websocket.base_url),
                        envelope.room_id,
                        message,
                        user,
                    )

                elif envelope.type == "edit":
                    if envelope.room_id is None or envelope.message_id is None or not envelope.content:
                        await websocket.send_json(
                            {"type": "error", "detail": "room_id, message_id, and content required"}
                        )
                        continue
                    if _missing_scope(api_token, "write:messages"):
                        await websocket.send_json(
                            {"type": "error", "detail": "Token missing required scope: write:messages"}
                        )
                        continue
                    if envelope.room_id not in joined_rooms or not await _is_room_member(
                        db, envelope.room_id, user.id
                    ):
                        await websocket.send_json(
                            {"type": "error", "detail": "Not a member of this room"}
                        )
                        continue
                    try:
                        message = await edit_message(db, envelope.message_id, user.id, envelope.content)
                    except MessageNotFoundError:
                        await websocket.send_json({"type": "error", "detail": "Message not found"})
                        continue
                    except NotMessageAuthorError:
                        await websocket.send_json(
                            {"type": "error", "detail": "You can only edit your own messages"}
                        )
                        continue
                    await broadcast_message_update(db, broadcaster, envelope.room_id, message)

                elif envelope.type == "delete":
                    if envelope.room_id is None or envelope.message_id is None:
                        await websocket.send_json(
                            {"type": "error", "detail": "room_id and message_id required"}
                        )
                        continue
                    if _missing_scope(api_token, "write:messages"):
                        await websocket.send_json(
                            {"type": "error", "detail": "Token missing required scope: write:messages"}
                        )
                        continue
                    if envelope.room_id not in joined_rooms or not await _is_room_member(
                        db, envelope.room_id, user.id
                    ):
                        await websocket.send_json(
                            {"type": "error", "detail": "Not a member of this room"}
                        )
                        continue
                    try:
                        await delete_message(db, envelope.message_id, user.id)
                    except MessageNotFoundError:
                        await websocket.send_json({"type": "error", "detail": "Message not found"})
                        continue
                    except NotMessageAuthorError:
                        await websocket.send_json(
                            {"type": "error", "detail": "You can only delete your own messages"}
                        )
                        continue
                    await broadcast_message_delete(broadcaster, envelope.room_id, envelope.message_id)

                elif envelope.type == "reaction":
                    if (
                        envelope.room_id is None
                        or envelope.message_id is None
                        or not envelope.emoji
                        # #18: a raw unicode glyph never gets close to this,
                        # but a custom emoji reaction is stored as its
                        # literal `:shortcode:` text (see MessageReaction.emoji's
                        # String(32) column, which this matches exactly).
                        or len(envelope.emoji) > 32
                    ):
                        await websocket.send_json(
                            {"type": "error", "detail": "room_id, message_id, and emoji required"}
                        )
                        continue
                    if _missing_scope(api_token, "write:messages"):
                        await websocket.send_json(
                            {"type": "error", "detail": "Token missing required scope: write:messages"}
                        )
                        continue
                    if envelope.room_id not in joined_rooms or not await _is_room_member(
                        db, envelope.room_id, user.id
                    ):
                        await websocket.send_json(
                            {"type": "error", "detail": "Not a member of this room"}
                        )
                        continue
                    target_message = await db.get(Message, envelope.message_id)
                    if (
                        target_message is None
                        or target_message.room_id != envelope.room_id
                        or target_message.deleted_at is not None
                    ):
                        await websocket.send_json({"type": "error", "detail": "Message not found"})
                        continue
                    reactions = await toggle_reaction(db, envelope.message_id, user.id, envelope.emoji)
                    await broadcast_reaction_update(
                        broadcaster, envelope.room_id, envelope.message_id, reactions
                    )

                else:
                    await websocket.send_json(
                        {"type": "error", "detail": f"Unknown message type: {envelope.type}"}
                    )
            finally:
                # See the comment on the pre-loop commit above -- guarantees
                # every single frame, on every exit path (including the
                # many `continue`s above, which still run a `finally`
                # before actually looping), leaves nothing open while this
                # blocks on the next receive_json().
                await db.commit()

    except WebSocketDisconnect:
        pass
    finally:
        manager.leave_all(websocket)
        manager.unregister_user(user.id, websocket)
        for room_id in joined_rooms:
            await _best_effort("room presence", presence.leave(room_id, user.id, conn_id))
        if is_blurred:
            await _best_effort("focus presence", focus_presence.mark_focused(user.id, conn_id))
        if await _best_effort("global presence", global_presence.disconnect(user.id, conn_id)):
            await _best_effort(
                "offline broadcast",
                _broadcast_offline(db, broadcaster, user.id),
            )
