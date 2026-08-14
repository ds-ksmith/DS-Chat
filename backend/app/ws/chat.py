import uuid

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import RoomMembership, User
from app.services.message_service import create_message

router = APIRouter(tags=["ws"])

WS_UNAUTHENTICATED = 4401


class ClientEnvelope(BaseModel):
    type: str
    room_id: uuid.UUID | None = None
    content: str | None = None


async def _is_room_member(db: AsyncSession, room_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    result = await db.execute(
        select(RoomMembership).where(
            RoomMembership.room_id == room_id, RoomMembership.user_id == user_id
        )
    )
    return result.scalar_one_or_none() is not None


@router.websocket("/ws/chat")
async def chat_endpoint(websocket: WebSocket, db: AsyncSession = Depends(get_db)) -> None:
    user_id_raw = websocket.session.get("user_id")
    if not user_id_raw:
        await websocket.close(code=WS_UNAUTHENTICATED)
        return

    user = await db.get(User, uuid.UUID(user_id_raw))
    if user is None:
        await websocket.close(code=WS_UNAUTHENTICATED)
        return

    await websocket.accept()
    manager = websocket.app.state.connection_manager
    joined_rooms: set[uuid.UUID] = set()

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
                joined_rooms.add(envelope.room_id)
                await websocket.send_json({"type": "joined", "room_id": str(envelope.room_id)})

            elif envelope.type == "leave":
                if envelope.room_id is None:
                    await websocket.send_json({"type": "error", "detail": "room_id required"})
                    continue
                manager.leave(envelope.room_id, websocket)
                joined_rooms.discard(envelope.room_id)

            elif envelope.type == "message":
                if envelope.room_id is None or not envelope.content:
                    await websocket.send_json(
                        {"type": "error", "detail": "room_id and content required"}
                    )
                    continue
                if envelope.room_id not in joined_rooms or not await _is_room_member(
                    db, envelope.room_id, user.id
                ):
                    await websocket.send_json(
                        {"type": "error", "detail": "Not a member of this room"}
                    )
                    continue
                message = await create_message(db, envelope.room_id, user.id, envelope.content)
                await manager.broadcast(
                    envelope.room_id,
                    {
                        "type": "message",
                        "id": str(message.id),
                        "room_id": str(message.room_id),
                        "user_id": str(message.user_id),
                        "username": user.username,
                        "content": message.content,
                        "created_at": message.created_at.isoformat(),
                    },
                )

            else:
                await websocket.send_json(
                    {"type": "error", "detail": f"Unknown message type: {envelope.type}"}
                )

    except WebSocketDisconnect:
        pass
    finally:
        manager.leave_all(websocket)
