import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Room, RoomMembership, RoomRole
from app.schemas.room import RoomCreate


class DuplicateRoomError(Exception):
    pass


class RoomNotFoundError(Exception):
    pass


class RoomIsPrivateError(Exception):
    pass


async def create_room(db: AsyncSession, owner_id: uuid.UUID, data: RoomCreate) -> Room:
    room = Room(name=data.name, description=data.description, owner_id=owner_id)
    db.add(room)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise DuplicateRoomError() from exc

    db.add(RoomMembership(room_id=room.id, user_id=owner_id, role=RoomRole.owner))
    await db.commit()
    await db.refresh(room)
    return room


async def list_open_rooms(db: AsyncSession, user_id: uuid.UUID) -> list[tuple[Room, bool]]:
    result = await db.execute(
        select(Room)
        .where(Room.is_private.is_(False))
        .options(selectinload(Room.memberships))
        .order_by(Room.created_at)
    )
    rooms = result.scalars().all()
    return [
        (room, any(m.user_id == user_id for m in room.memberships)) for room in rooms
    ]


async def get_room(db: AsyncSession, room_id: uuid.UUID) -> Room:
    room = await db.get(Room, room_id)
    if room is None:
        raise RoomNotFoundError()
    return room


async def join_room(db: AsyncSession, room_id: uuid.UUID, user_id: uuid.UUID) -> RoomMembership:
    room = await get_room(db, room_id)
    if room.is_private:
        raise RoomIsPrivateError()

    result = await db.execute(
        select(RoomMembership).where(
            RoomMembership.room_id == room_id, RoomMembership.user_id == user_id
        )
    )
    membership = result.scalar_one_or_none()
    if membership is not None:
        return membership

    membership = RoomMembership(room_id=room_id, user_id=user_id, role=RoomRole.member)
    db.add(membership)
    await db.commit()
    await db.refresh(membership)
    return membership
