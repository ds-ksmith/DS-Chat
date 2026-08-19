import uuid

from sqlalchemy import delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    EventSubscription,
    Message,
    MessageFile,
    MessageImage,
    MessageMention,
    MessageReaction,
    MessageRoomReference,
    Room,
    RoomMembership,
    RoomRole,
    User,
    WebhookIncoming,
)
from app.schemas.room import RoomCreate, RoomUpdate
from app.services.email_service import send_email
from app.storage import delete_file


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


class TargetUserNotFoundError(Exception):
    pass


class AlreadyMemberError(Exception):
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
        .where(Room.is_private.is_(False), Room.is_archived.is_(False))
        .options(selectinload(Room.memberships))
        .order_by(Room.created_at, Room.id)
    )
    rooms = result.scalars().all()
    return [
        (room, any(m.user_id == user_id for m in room.memberships)) for room in rooms
    ]


async def list_member_rooms(
    db: AsyncSession, user_id: uuid.UUID
) -> list[tuple[Room, RoomRole, bool, bool]]:
    last_message_at = (
        select(func.max(Message.created_at))
        .where(Message.room_id == Room.id)
        .correlate(Room)
        .scalar_subquery()
    )
    # Unread AND mentions this user specifically -- a stronger signal than
    # plain has_unread, surfaced as its own field so the sidebar can show a
    # visually distinct badge instead of (not alongside) the plain dot.
    has_unread_mention = (
        select(MessageMention.message_id)
        .join(Message, Message.id == MessageMention.message_id)
        .where(
            MessageMention.user_id == user_id,
            Message.room_id == Room.id,
            Message.created_at > RoomMembership.last_read_at,
        )
        .correlate(Room, RoomMembership)
        .exists()
    )
    result = await db.execute(
        select(
            Room, RoomMembership.role, RoomMembership.last_read_at, last_message_at, has_unread_mention
        )
        .join(RoomMembership, RoomMembership.room_id == Room.id)
        .where(RoomMembership.user_id == user_id)
        # A secondary key on the primary key -- without it, Postgres has no
        # obligation to return two same-instant rooms (a plausible tie:
        # bulk-created/migrated rooms, or just two created in quick
        # succession) in the same order on every call, which without a
        # stable order can visibly reshuffle the sidebar between one
        # device's fetch and another's.
        .order_by(Room.created_at, Room.id)
    )
    return [
        (room, role, last_message_at is not None and last_message_at > last_read_at, has_mention)
        for room, role, last_read_at, last_message_at, has_mention in result.all()
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


async def add_member(
    db: AsyncSession, room: Room, target_user_id: uuid.UUID, base_url: str
) -> RoomMembership:
    target = await db.get(User, target_user_id)
    if target is None:
        raise TargetUserNotFoundError()

    existing = await db.execute(
        select(RoomMembership).where(
            RoomMembership.room_id == room.id, RoomMembership.user_id == target_user_id
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise AlreadyMemberError()

    membership = RoomMembership(room_id=room.id, user_id=target_user_id, role=RoomRole.member)
    db.add(membership)
    await db.commit()

    await send_email(
        db,
        target.email,
        f"You've been added to #{room.name}",
        f"You've been added to the #{room.name} room on DS Chat.\n\n"
        f"Open the app: {base_url.rstrip('/')}",
    )

    result = await db.execute(
        select(RoomMembership)
        .where(RoomMembership.room_id == room.id, RoomMembership.user_id == target_user_id)
        .options(selectinload(RoomMembership.user))
    )
    return result.scalar_one()


async def update_room(db: AsyncSession, room: Room, data: RoomUpdate) -> Room:
    if data.name is not None:
        room.name = data.name
    if data.description is not None:
        room.description = data.description
    if data.is_private is not None:
        room.is_private = data.is_private
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise DuplicateRoomError() from exc
    await db.refresh(room)
    return room


async def delete_room(db: AsyncSession, room: Room) -> None:
    # Explicit deletes rather than relying on ORM cascade + eager-loading —
    # simpler and more predictable in async code. None of these FKs are
    # declared ON DELETE CASCADE at the DB level (confirmed across every
    # migration that added one), so every table referencing this room --
    # directly, or indirectly via one of its messages -- has to be cleared
    # explicitly, in dependency order, or the final room delete 500s on
    # whichever one it happens to hit first (originally surfaced as a
    # message_room_references FK violation, but every table below has the
    # exact same gap).
    room_message_ids = select(Message.id).where(Message.room_id == room.id).scalar_subquery()

    # Message-child tables first -- these reference message_id, so they'd
    # block deleting this room's own messages otherwise.
    await db.execute(delete(MessageMention).where(MessageMention.message_id.in_(room_message_ids)))
    await db.execute(delete(MessageReaction).where(MessageReaction.message_id.in_(room_message_ids)))
    # Both directions: a reference *from* one of this room's own messages,
    # and a reference *to* this room from a message in a completely
    # different room (the case that originally surfaced this bug).
    await db.execute(
        delete(MessageRoomReference).where(
            or_(
                MessageRoomReference.message_id.in_(room_message_ids),
                MessageRoomReference.room_id == room.id,
            )
        )
    )

    # Fetch attachment storage filenames before deleting their rows -- the
    # actual files are only unlinked after a successful commit below, so a
    # rolled-back transaction never leaves us having destroyed something we
    # couldn't get back.
    image_filenames = (
        await db.execute(select(MessageImage.storage_filename).where(MessageImage.room_id == room.id))
    ).scalars().all()
    file_filenames = (
        await db.execute(select(MessageFile.storage_filename).where(MessageFile.room_id == room.id))
    ).scalars().all()

    # Messages themselves, now that nothing still references them.
    await db.execute(delete(Message).where(Message.room_id == room.id))

    # Room-scoped attachments/integrations -- messages.image_id/file_id
    # reference these, so they must come after the message delete above.
    await db.execute(delete(MessageImage).where(MessageImage.room_id == room.id))
    await db.execute(delete(MessageFile).where(MessageFile.room_id == room.id))
    await db.execute(delete(WebhookIncoming).where(WebhookIncoming.room_id == room.id))
    await db.execute(delete(EventSubscription).where(EventSubscription.room_id == room.id))

    await db.execute(delete(RoomMembership).where(RoomMembership.room_id == room.id))
    await db.delete(room)
    await db.commit()

    for filename in (*image_filenames, *file_filenames):
        delete_file(filename)


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


async def mark_room_read(db: AsyncSession, room_id: uuid.UUID, user_id: uuid.UUID) -> None:
    membership = await _get_membership(db, room_id, user_id)
    membership.last_read_at = func.now()
    await db.commit()


async def leave_room(db: AsyncSession, room_id: uuid.UUID, user_id: uuid.UUID) -> None:
    membership = await _get_membership(db, room_id, user_id)
    if membership.role == RoomRole.owner:
        raise OwnerMustTransferError()

    await db.delete(membership)
    await db.commit()
