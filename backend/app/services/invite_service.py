import secrets
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import InviteStatus, RoomInvite, RoomMembership, RoomRole, User


class TargetUserNotFoundError(Exception):
    pass


class AlreadyMemberError(Exception):
    pass


class DuplicateInviteError(Exception):
    pass


class InviteNotFoundError(Exception):
    pass


class WrongInviteTargetError(Exception):
    pass


class InviteNotPendingError(Exception):
    pass


class InviteExpiredError(Exception):
    pass


async def create_invite(
    db: AsyncSession, room_id: uuid.UUID, invited_by: uuid.UUID, target_username: str
) -> RoomInvite:
    result = await db.execute(select(User).where(User.username == target_username))
    target = result.scalar_one_or_none()
    if target is None:
        raise TargetUserNotFoundError()

    existing_membership = await db.execute(
        select(RoomMembership).where(
            RoomMembership.room_id == room_id, RoomMembership.user_id == target.id
        )
    )
    if existing_membership.scalar_one_or_none() is not None:
        raise AlreadyMemberError()

    existing_invite = await db.execute(
        select(RoomInvite).where(
            RoomInvite.room_id == room_id,
            RoomInvite.target_user_id == target.id,
            RoomInvite.status == InviteStatus.pending,
        )
    )
    if existing_invite.scalar_one_or_none() is not None:
        raise DuplicateInviteError()

    invite = RoomInvite(
        room_id=room_id,
        invited_by=invited_by,
        token=secrets.token_urlsafe(32),
        target_user_id=target.id,
    )
    db.add(invite)
    await db.commit()
    await db.refresh(invite)
    return invite


async def list_room_invites(db: AsyncSession, room_id: uuid.UUID) -> list[RoomInvite]:
    result = await db.execute(
        select(RoomInvite).where(
            RoomInvite.room_id == room_id, RoomInvite.status == InviteStatus.pending
        )
    )
    return list(result.scalars().all())


async def list_my_invites(db: AsyncSession, user_id: uuid.UUID) -> list[RoomInvite]:
    result = await db.execute(
        select(RoomInvite)
        .where(
            RoomInvite.target_user_id == user_id,
            RoomInvite.status == InviteStatus.pending,
            RoomInvite.expires_at > datetime.now(timezone.utc),
        )
        .options(selectinload(RoomInvite.room))
    )
    return list(result.scalars().all())


async def _get_invite(db: AsyncSession, invite_id: uuid.UUID) -> RoomInvite:
    invite = await db.get(RoomInvite, invite_id)
    if invite is None:
        raise InviteNotFoundError()
    return invite


async def accept_invite(db: AsyncSession, invite_id: uuid.UUID, user_id: uuid.UUID) -> RoomMembership:
    invite = await _get_invite(db, invite_id)
    if invite.target_user_id != user_id:
        raise WrongInviteTargetError()
    if invite.status != InviteStatus.pending:
        raise InviteNotPendingError()
    if invite.expires_at <= datetime.now(timezone.utc):
        raise InviteExpiredError()

    result = await db.execute(
        select(RoomMembership).where(
            RoomMembership.room_id == invite.room_id, RoomMembership.user_id == user_id
        )
    )
    membership = result.scalar_one_or_none()
    if membership is None:
        membership = RoomMembership(room_id=invite.room_id, user_id=user_id, role=RoomRole.member)
        db.add(membership)

    invite.status = InviteStatus.accepted
    await db.commit()
    await db.refresh(membership)
    return membership


async def decline_invite(db: AsyncSession, invite_id: uuid.UUID, user_id: uuid.UUID) -> RoomInvite:
    invite = await _get_invite(db, invite_id)
    if invite.target_user_id != user_id:
        raise WrongInviteTargetError()
    if invite.status != InviteStatus.pending:
        raise InviteNotPendingError()

    invite.status = InviteStatus.revoked
    await db.commit()
    await db.refresh(invite)
    return invite


async def revoke_invite(db: AsyncSession, room_id: uuid.UUID, invite_id: uuid.UUID) -> RoomInvite:
    invite = await _get_invite(db, invite_id)
    if invite.room_id != room_id:
        raise InviteNotFoundError()
    if invite.status != InviteStatus.pending:
        raise InviteNotPendingError()

    invite.status = InviteStatus.revoked
    await db.commit()
    await db.refresh(invite)
    return invite
