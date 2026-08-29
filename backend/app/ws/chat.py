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

router = APIRouter(tags=["ws"])

WS_UNAUTHENTICATED = 4401


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
    manager.register_user(user.id, websocket)
    # Only broadcast on a genuine offline->online transition (this user's
    # first open connection), not for every extra tab -- broadcast_member_
    # updated tells every room this user's in to refresh, which would be
    # wasted churn on a transition that didn't actually change anything
    # visible.
    if await global_presence.connect(user.id):
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

    try:
        while True:
            raw = await websocket.receive_json()
            try:
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
                    await presence.join(envelope.room_id, user.id)
                    joined_rooms.add(envelope.room_id)
                    await websocket.send_json({"type": "joined", "room_id": str(envelope.room_id)})

                elif envelope.type == "leave":
                    if envelope.room_id is None:
                        await websocket.send_json({"type": "error", "detail": "room_id required"})
                        continue
                    manager.leave(envelope.room_id, websocket)
                    await presence.leave(envelope.room_id, user.id)
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
                            await focus_presence.mark_focused(user.id)
                            is_blurred = False
                    else:
                        if not is_blurred:
                            await focus_presence.mark_blurred(user.id)
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
            await presence.leave(room_id, user.id)
        if is_blurred:
            await focus_presence.mark_focused(user.id)
        if await global_presence.disconnect(user.id):
            await broadcast_member_updated(db, broadcaster, user.id)
            await broadcast_dm_presence_update(db, broadcaster, user.id, online=False)
