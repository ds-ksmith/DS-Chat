import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Room, RoomMembership, RoomRole, User
from app.security import hash_password
from app.services.audit import record_audit_log


class UserNotFoundError(Exception):
    pass


class RoomNotFoundError(Exception):
    pass


class CannotActOnSelfError(Exception):
    pass


class TargetNotRoomMemberError(Exception):
    pass


async def _get_user(db: AsyncSession, user_id: uuid.UUID) -> User:
    user = await db.get(User, user_id)
    if user is None:
        raise UserNotFoundError()
    return user


async def _get_room(db: AsyncSession, room_id: uuid.UUID) -> Room:
    room = await db.get(Room, room_id)
    if room is None:
        raise RoomNotFoundError()
    return room


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
        raise TargetNotRoomMemberError()
    return membership


async def list_users(db: AsyncSession) -> list[User]:
    result = await db.execute(select(User).order_by(User.created_at))
    return list(result.scalars().all())


async def set_user_active(
    db: AsyncSession, actor: User, target_user_id: uuid.UUID, active: bool
) -> User:
    if target_user_id == actor.id:
        raise CannotActOnSelfError()
    user = await _get_user(db, target_user_id)
    user.is_active = active
    record_audit_log(db, actor, "user.activate" if active else "user.deactivate", "user", user.id)
    await db.commit()
    await db.refresh(user)
    return user


async def reset_user_password(
    db: AsyncSession, actor: User, target_user_id: uuid.UUID, new_password: str
) -> None:
    user = await _get_user(db, target_user_id)
    user.password_hash = hash_password(new_password)
    record_audit_log(db, actor, "user.reset_password", "user", user.id)
    await db.commit()


async def set_user_site_admin(
    db: AsyncSession, actor: User, target_user_id: uuid.UUID, is_admin: bool
) -> User:
    if target_user_id == actor.id:
        raise CannotActOnSelfError()
    user = await _get_user(db, target_user_id)
    user.is_site_admin = is_admin
    record_audit_log(db, actor, "user.promote" if is_admin else "user.demote", "user", user.id)
    await db.commit()
    await db.refresh(user)
    return user


async def list_rooms_admin(db: AsyncSession) -> list[tuple[Room, int]]:
    # #52: DMs are fully private, not just unlisted -- excluded here rather
    # than merely omitted from the response, so there's no admin-portal
    # surface (this list, or the audit log via anything that touches this
    # query) that reveals a DM even exists between two users.
    result = await db.execute(
        select(Room, func.count(RoomMembership.user_id))
        .outerjoin(RoomMembership, RoomMembership.room_id == Room.id)
        .where(Room.is_dm.is_(False))
        .group_by(Room.id)
        .order_by(Room.created_at)
    )
    return [(room, count) for room, count in result.all()]


async def set_room_archived(
    db: AsyncSession, actor: User, room_id: uuid.UUID, archived: bool
) -> Room:
    room = await _get_room(db, room_id)
    room.is_archived = archived
    record_audit_log(db, actor, "room.archive" if archived else "room.unarchive", "room", room.id)
    await db.commit()
    await db.refresh(room)
    return room


async def transfer_ownership_admin(
    db: AsyncSession, actor: User, room_id: uuid.UUID, new_owner_id: uuid.UUID
) -> Room:
    room = await _get_room(db, room_id)
    # Same invariant as the member-initiated room_service.transfer_ownership
    # (new owner must already be a member) -- this is the admin override for
    # the "acting user must currently be the owner" gate, not for that one.
    new_owner_membership = await _get_membership(db, room_id, new_owner_id)
    current_owner_membership = await _get_membership(db, room_id, room.owner_id)

    new_owner_membership.role = RoomRole.owner
    current_owner_membership.role = RoomRole.admin
    room.owner_id = new_owner_id
    record_audit_log(
        db,
        actor,
        "room.transfer_ownership",
        "room",
        room.id,
        {"new_owner_id": str(new_owner_id)},
    )
    await db.commit()
    await db.refresh(room)
    return room
