import uuid

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import ApiToken, Message, MessageFile, MessageImage, RoomMembership, User
from app.services.bot_service import resolve_token
from app.services.message_events import (
    broadcast_message_update,
    broadcast_new_message,
    broadcast_reaction_update,
)
from app.services.message_service import (
    MessageNotFoundError,
    NotMessageAuthorError,
    create_message,
    edit_message,
    toggle_reaction,
)

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


async def _is_room_member(db: AsyncSession, room_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    result = await db.execute(
        select(RoomMembership).where(
            RoomMembership.room_id == room_id, RoomMembership.user_id == user_id
        )
    )
    return result.scalar_one_or_none() is not None


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
        user_id_raw = websocket.session.get("user_id")
        if not user_id_raw:
            await websocket.close(code=WS_UNAUTHENTICATED)
            return
        user = await db.get(User, uuid.UUID(user_id_raw))
        if user is None or not user.is_active:
            await websocket.close(code=WS_UNAUTHENTICATED)
            return

    await websocket.accept()
    manager = websocket.app.state.connection_manager
    presence = websocket.app.state.presence
    broadcaster = websocket.app.state.broadcaster
    joined_rooms: set[uuid.UUID] = set()
    manager.register_user(user.id, websocket)

    try:
        while True:
            raw = await websocket.receive_json()
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
                await broadcast_new_message(db, broadcaster, presence, envelope.room_id, message, user)

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

            elif envelope.type == "reaction":
                if (
                    envelope.room_id is None
                    or envelope.message_id is None
                    or not envelope.emoji
                    or len(envelope.emoji) > 8
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
                if target_message is None or target_message.room_id != envelope.room_id:
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

    except WebSocketDisconnect:
        pass
    finally:
        manager.leave_all(websocket)
        manager.unregister_user(user.id, websocket)
        for room_id in joined_rooms:
            await presence.leave(room_id, user.id)
