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


class CannotDmSelfError(Exception):
    pass


class CannotModifyDmError(Exception):
    pass


class NotADmError(Exception):
    pass


def dm_room_name(user_a_id: uuid.UUID, user_b_id: uuid.UUID) -> str:
    """Deterministic, internal-only name for the DM room between these two
    users -- same canonical string regardless of argument order, so
    find_or_create_dm can look up an existing DM with a single indexed
    query (Room.name is already unique+indexed) instead of a membership-set
    join. Never shown to a user -- the frontend renders a DM's dm_partner
    info instead of its `name` (see MyRoomItem)."""
    ids = sorted((str(user_a_id), str(user_b_id)))
    return f"dm:{ids[0]}:{ids[1]}"


async def _unhide(db: AsyncSession, room_id: uuid.UUID, user_id: uuid.UUID) -> None:
    membership = (
        await db.execute(
            select(RoomMembership).where(
                RoomMembership.room_id == room_id, RoomMembership.user_id == user_id
            )
        )
    ).scalar_one_or_none()
    if membership is not None and membership.hidden_at is not None:
        membership.hidden_at = None
        await db.commit()


async def hide_dm(db: AsyncSession, room: Room, user_id: uuid.UUID) -> None:
    if not room.is_dm:
        raise NotADmError()
    membership = await _get_membership(db, room.id, user_id)
    membership.hidden_at = func.now()
    await db.commit()


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


async def find_or_create_dm(db: AsyncSession, user_id: uuid.UUID, other_user_id: uuid.UUID) -> Room:
    if user_id == other_user_id:
        raise CannotDmSelfError()
    other = await db.get(User, other_user_id)
    if other is None:
        raise TargetUserNotFoundError()

    name = dm_room_name(user_id, other_user_id)
    result = await db.execute(select(Room).where(Room.name == name))
    room = result.scalar_one_or_none()
    if room is not None:
        await _unhide(db, room.id, user_id)
        return room

    # is_private=True is belt-and-suspenders here -- list_open_rooms also
    # excludes is_dm directly -- but it's also just semantically correct: a
    # DM genuinely is a private room. Both participants get the plain
    # `member` role (there's no meaningful owner/admin distinction for a
    # 1:1 DM); `owner_id` still has to be someone to satisfy the column,
    # but nothing reads it as meaningful for a DM.
    room = Room(name=name, is_private=True, is_dm=True, owner_id=user_id)
    db.add(room)
    try:
        await db.flush()
    except IntegrityError:
        # Lost a race with a concurrent find_or_create_dm for the same pair
        # (e.g. both people click "message" on each other at once) -- the
        # unique constraint on `name` is exactly what caught it, same
        # pattern as create_room's DuplicateRoomError. The row that won the
        # race is the room we actually want.
        await db.rollback()
        result = await db.execute(select(Room).where(Room.name == name))
        room = result.scalar_one()
        await _unhide(db, room.id, user_id)
        return room

    db.add(RoomMembership(room_id=room.id, user_id=user_id, role=RoomRole.member))
    db.add(RoomMembership(room_id=room.id, user_id=other_user_id, role=RoomRole.member))
    await db.commit()
    await db.refresh(room)
    return room


async def list_open_rooms(db: AsyncSession, user_id: uuid.UUID) -> list[tuple[Room, bool]]:
    result = await db.execute(
        select(Room)
        .where(Room.is_private.is_(False), Room.is_archived.is_(False), Room.is_dm.is_(False))
        .options(selectinload(Room.memberships))
        .order_by(Room.created_at, Room.id)
    )
    rooms = result.scalars().all()
    return [
        (room, any(m.user_id == user_id for m in room.memberships)) for room in rooms
    ]


async def list_member_rooms(
    db: AsyncSession, user_id: uuid.UUID
) -> list[tuple[Room, RoomRole, bool, bool, User | None]]:
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
        .where(RoomMembership.user_id == user_id, RoomMembership.hidden_at.is_(None))
        # A secondary key on the primary key -- without it, Postgres has no
        # obligation to return two same-instant rooms (a plausible tie:
        # bulk-created/migrated rooms, or just two created in quick
        # succession) in the same order on every call, which without a
        # stable order can visibly reshuffle the sidebar between one
        # device's fetch and another's.
        .order_by(Room.created_at, Room.id)
    )
    rows = result.all()

    # #52: one batched follow-up query for every DM room's *other*
    # participant, rather than a fetch per row -- a DM only ever has
    # exactly two members, so "the other one" is unambiguous.
    dm_room_ids = [room.id for room, *_ in rows if room.is_dm]
    partners_by_room: dict[uuid.UUID, User] = {}
    if dm_room_ids:
        partner_result = await db.execute(
            select(RoomMembership.room_id, User)
            .join(User, User.id == RoomMembership.user_id)
            .where(RoomMembership.room_id.in_(dm_room_ids), RoomMembership.user_id != user_id)
        )
        partners_by_room = {room_id: user for room_id, user in partner_result.all()}

    return [
        (
            room,
            role,
            last_message_at is not None and last_message_at > last_read_at,
            has_mention,
            partners_by_room.get(room.id),
        )
        for room, role, last_read_at, last_message_at, has_mention in rows
    ]


async def list_dm_partner_ids(db: AsyncSession, user_id: uuid.UUID) -> list[uuid.UUID]:
    """Every user this user_id shares a DM with (#63) -- used to know who
    needs telling about a global online/offline transition, since Presence
    gates room-channel delivery on actually having that specific room
    joined right now (only ever the one room currently open in the UI), so
    a DM sitting unopened in the sidebar would otherwise never hear about
    its partner's status changing at all."""
    result = await db.execute(
        select(RoomMembership.user_id)
        .join(Room, Room.id == RoomMembership.room_id)
        .where(
            Room.is_dm.is_(True),
            RoomMembership.user_id != user_id,
            RoomMembership.room_id.in_(
                select(RoomMembership.room_id).where(RoomMembership.user_id == user_id)
            ),
        )
    )
    return [row[0] for row in result.all()]


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
    # A DM's `name` is an internal token find_or_create_dm's lookup depends
    # on being stable -- renaming it (even via the #48 site-admin bypass in
    # the router) would silently orphan that invariant, not just leak a
    # detail that's supposed to stay private. Blocked here, not just in the
    # UI, since it's a correctness issue for every caller, not a permission
    # one.
    if room.is_dm:
        raise CannotModifyDmError()
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
