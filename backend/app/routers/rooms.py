import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user, require_room_member
from app.models import User
from app.schemas.message import MessageRead
from app.schemas.room import RoomCreate, RoomListItem, RoomRead
from app.services.message_service import list_recent_messages
from app.services.room_service import (
    DuplicateRoomError,
    RoomIsPrivateError,
    RoomNotFoundError,
    create_room,
    get_room,
    join_room,
    list_open_rooms,
)

router = APIRouter(prefix="/api/rooms", tags=["rooms"])


@router.post("", response_model=RoomRead, status_code=201)
async def create_room_endpoint(
    data: RoomCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await create_room(db, current_user.id, data)
    except DuplicateRoomError:
        raise HTTPException(status_code=409, detail="A room with this name already exists")


@router.get("", response_model=list[RoomListItem])
async def list_rooms_endpoint(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rooms = await list_open_rooms(db, current_user.id)
    return [
        RoomListItem(
            id=room.id,
            name=room.name,
            description=room.description,
            is_private=room.is_private,
            owner_id=room.owner_id,
            created_at=room.created_at,
            is_member=is_member,
        )
        for room, is_member in rooms
    ]


@router.post("/{room_id}/join", response_model=RoomRead)
async def join_room_endpoint(
    room_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await join_room(db, room_id, current_user.id)
        return await get_room(db, room_id)
    except RoomNotFoundError:
        raise HTTPException(status_code=404, detail="Room not found")
    except RoomIsPrivateError:
        raise HTTPException(status_code=400, detail="Cannot join a private room directly")


@router.get("/{room_id}/messages", response_model=list[MessageRead])
async def get_room_messages_endpoint(
    room_id: uuid.UUID,
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_room_member(room_id, current_user, db)
    return await list_recent_messages(db, room_id, limit)
