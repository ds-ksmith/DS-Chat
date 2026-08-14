import uuid

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Message, Room, RoomInvite, RoomMembership, RoomRole
from app.schemas.room import RoomCreate, RoomUpdate


class DuplicateRoomError(Exception):
    pass


class RoomNotFoundError(Exception):
    pass


class RoomIsPrivateError(Exception):
    pass


class MembershipNotFoundError(Exception):
    pass


class CannotRemoveOwnerError(Exception):
    pass


class InsufficientRoleError(Exception):
    pass


class OwnerMustTransferError(Exception):
    pass


async def create_room(db: AsyncSession, owner_id: uuid.UUID, data: RoomCreate) -> Room:
    room = Room(
        name=data.name,
        description=data.description,
        is_private=data.is_private,
        owner_id=owner_id,
    )
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


async def list_member_rooms(db: AsyncSession, user_id: uuid.UUID) -> list[tuple[Room, RoomRole]]:
    result = await db.execute(
        select(Room, RoomMembership.role)
        .join(RoomMembership, RoomMembership.room_id == Room.id)
        .where(RoomMembership.user_id == user_id)
        .order_by(Room.created_at)
    )
    return [(room, role) for room, role in result.all()]


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


async def update_room(db: AsyncSession, room: Room, data: RoomUpdate) -> Room:
    if data.name is not None:
        room.name = data.name
    if data.description is not None:
        room.description = data.description
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise DuplicateRoomError() from exc
    await db.refresh(room)
    return room


async def delete_room(db: AsyncSession, room: Room) -> None:
    # Explicit deletes rather than relying on ORM cascade + eager-loading —
    # simpler and more predictable in async code.
    await db.execute(delete(Message).where(Message.room_id == room.id))
    await db.execute(delete(RoomInvite).where(RoomInvite.room_id == room.id))
    await db.execute(delete(RoomMembership).where(RoomMembership.room_id == room.id))
    await db.delete(room)
    await db.commit()


async def list_room_members(db: AsyncSession, room_id: uuid.UUID) -> list[RoomMembership]:
    result = await db.execute(
        select(RoomMembership)
        .where(RoomMembership.room_id == room_id)
        .options(selectinload(RoomMembership.user))
        .order_by(RoomMembership.joined_at)
    )
    return list(result.scalars().all())


async def _get_membership(
    db: AsyncSession, room_id: uuid.UUID, user_id: uuid.UUID
) -> RoomMembership:
    result = await db.execute(
        select(RoomMembership).where(
            RoomMembership.room_id == room_id, RoomMembership.user_id == user_id
        )
    )
    membership = result.scalar_one_or_none()
    if membership is None:
        raise MembershipNotFoundError()
    return membership


async def remove_member(
    db: AsyncSession, room_id: uuid.UUID, target_user_id: uuid.UUID, acting_role: RoomRole
) -> None:
    membership = await _get_membership(db, room_id, target_user_id)
    if membership.role == RoomRole.owner:
        raise CannotRemoveOwnerError()
    if membership.role == RoomRole.admin and acting_role != RoomRole.owner:
        raise InsufficientRoleError()

    await db.delete(membership)
    await db.commit()


async def change_member_role(
    db: AsyncSession, room_id: uuid.UUID, target_user_id: uuid.UUID, new_role: RoomRole
) -> RoomMembership:
    membership = await _get_membership(db, room_id, target_user_id)
    if membership.role == RoomRole.owner or new_role == RoomRole.owner:
        # Ownership changes only happen through transfer_ownership.
        raise InsufficientRoleError()

    membership.role = new_role
    await db.commit()
    result = await db.execute(
        select(RoomMembership)
        .where(RoomMembership.room_id == room_id, RoomMembership.user_id == target_user_id)
        .options(selectinload(RoomMembership.user))
    )
    return result.scalar_one()


async def transfer_ownership(
    db: AsyncSession, room: Room, current_owner_id: uuid.UUID, new_owner_user_id: uuid.UUID
) -> Room:
    new_owner_membership = await _get_membership(db, room.id, new_owner_user_id)
    current_owner_membership = await _get_membership(db, room.id, current_owner_id)

    new_owner_membership.role = RoomRole.owner
    current_owner_membership.role = RoomRole.admin
    room.owner_id = new_owner_user_id
    await db.commit()
    await db.refresh(room)
    return room


async def leave_room(db: AsyncSession, room_id: uuid.UUID, user_id: uuid.UUID) -> None:
    membership = await _get_membership(db, room_id, user_id)
    if membership.role == RoomRole.owner:
        raise OwnerMustTransferError()

    await db.delete(membership)
    await db.commit()
