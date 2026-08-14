import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user, require_room_member, require_room_role
from app.models import RoomRole, User
from app.schemas.invite import InviteCreate, InviteRead
from app.schemas.message import MessageRead
from app.schemas.room import (
    MyRoomItem,
    RoomCreate,
    RoomListItem,
    RoomMemberRead,
    RoomMemberRoleUpdate,
    RoomRead,
    RoomUpdate,
    TransferOwnershipRequest,
)
from app.services.invite_service import (
    AlreadyMemberError,
    DuplicateInviteError,
    InviteNotFoundError,
    InviteNotPendingError,
    TargetUserNotFoundError,
    create_invite,
    list_room_invites,
    revoke_invite,
)
from app.services.message_service import list_recent_messages
from app.services.room_service import (
    CannotRemoveOwnerError,
    DuplicateRoomError,
    InsufficientRoleError,
    MembershipNotFoundError,
    OwnerMustTransferError,
    RoomIsPrivateError,
    RoomNotFoundError,
    change_member_role,
    create_room,
    delete_room,
    get_room,
    join_room,
    leave_room,
    list_member_rooms,
    list_open_rooms,
    list_room_members,
    remove_member,
    transfer_ownership,
    update_room,
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


@router.get("/mine", response_model=list[MyRoomItem])
async def list_my_rooms_endpoint(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rooms = await list_member_rooms(db, current_user.id)
    return [
        MyRoomItem(
            id=room.id,
            name=room.name,
            description=room.description,
            is_private=room.is_private,
            owner_id=room.owner_id,
            created_at=room.created_at,
            role=role,
        )
        for room, role in rooms
    ]


@router.patch("/{room_id}", response_model=RoomRead)
async def update_room_endpoint(
    room_id: uuid.UUID,
    data: RoomUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        room = await get_room(db, room_id)
        await require_room_role(room_id, current_user, db, RoomRole.admin)
        return await update_room(db, room, data)
    except RoomNotFoundError:
        raise HTTPException(status_code=404, detail="Room not found")
    except DuplicateRoomError:
        raise HTTPException(status_code=409, detail="A room with this name already exists")


@router.delete("/{room_id}", status_code=204)
async def delete_room_endpoint(
    room_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        room = await get_room(db, room_id)
        await require_room_role(room_id, current_user, db, RoomRole.owner)
        await delete_room(db, room)
    except RoomNotFoundError:
        raise HTTPException(status_code=404, detail="Room not found")


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


@router.post("/{room_id}/leave", status_code=204)
async def leave_room_endpoint(
    room_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_room_member(room_id, current_user, db)
    try:
        await leave_room(db, room_id, current_user.id)
    except OwnerMustTransferError:
        raise HTTPException(
            status_code=400, detail="Transfer ownership before leaving this room"
        )
    except MembershipNotFoundError:
        raise HTTPException(status_code=404, detail="Not a member of this room")


@router.get("/{room_id}/members", response_model=list[RoomMemberRead])
async def list_room_members_endpoint(
    room_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_room_member(room_id, current_user, db)
    memberships = await list_room_members(db, room_id)
    return [
        RoomMemberRead(
            user_id=m.user_id, username=m.user.username, role=m.role, joined_at=m.joined_at
        )
        for m in memberships
    ]


@router.delete("/{room_id}/members/{user_id}", status_code=204)
async def remove_member_endpoint(
    room_id: uuid.UUID,
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    membership = await require_room_role(room_id, current_user, db, RoomRole.admin)
    try:
        await remove_member(db, room_id, user_id, acting_role=membership.role)
    except MembershipNotFoundError:
        raise HTTPException(status_code=404, detail="That user is not a member of this room")
    except CannotRemoveOwnerError:
        raise HTTPException(
            status_code=400, detail="Room owner must transfer ownership before being removed"
        )
    except InsufficientRoleError:
        raise HTTPException(status_code=403, detail="Only the owner can remove an admin")


@router.patch("/{room_id}/members/{user_id}", response_model=RoomMemberRead)
async def change_member_role_endpoint(
    room_id: uuid.UUID,
    user_id: uuid.UUID,
    data: RoomMemberRoleUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_room_role(room_id, current_user, db, RoomRole.owner)
    try:
        membership = await change_member_role(db, room_id, user_id, data.role)
    except MembershipNotFoundError:
        raise HTTPException(status_code=404, detail="That user is not a member of this room")
    except InsufficientRoleError:
        raise HTTPException(
            status_code=400, detail="Use transfer-ownership to change the room owner"
        )
    return RoomMemberRead(
        user_id=membership.user_id,
        username=membership.user.username,
        role=membership.role,
        joined_at=membership.joined_at,
    )


@router.post("/{room_id}/transfer-ownership", response_model=RoomRead)
async def transfer_ownership_endpoint(
    room_id: uuid.UUID,
    data: TransferOwnershipRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        room = await get_room(db, room_id)
        await require_room_role(room_id, current_user, db, RoomRole.owner)
        return await transfer_ownership(db, room, current_user.id, data.new_owner_user_id)
    except RoomNotFoundError:
        raise HTTPException(status_code=404, detail="Room not found")
    except MembershipNotFoundError:
        raise HTTPException(
            status_code=404, detail="The new owner must already be a member of this room"
        )


@router.get("/{room_id}/messages", response_model=list[MessageRead])
async def get_room_messages_endpoint(
    room_id: uuid.UUID,
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_room_member(room_id, current_user, db)
    messages = await list_recent_messages(db, room_id, limit)
    return [
        MessageRead(
            id=m.id,
            room_id=m.room_id,
            user_id=m.user_id,
            username=m.user.username,
            content=m.content,
            created_at=m.created_at,
        )
        for m in messages
    ]


def _to_invite_read(invite) -> InviteRead:
    return InviteRead(
        id=invite.id,
        room_id=invite.room_id,
        invited_by=invite.invited_by,
        target_user_id=invite.target_user_id,
        target_username=invite.target_user.username if invite.target_user else None,
        status=invite.status,
        expires_at=invite.expires_at,
        created_at=invite.created_at,
    )


@router.post("/{room_id}/invites", response_model=InviteRead, status_code=201)
async def create_invite_endpoint(
    room_id: uuid.UUID,
    data: InviteCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_room_role(room_id, current_user, db, RoomRole.admin)
    try:
        invite = await create_invite(db, room_id, current_user.id, data.target_username)
    except TargetUserNotFoundError:
        raise HTTPException(status_code=404, detail="No user with that username")
    except AlreadyMemberError:
        raise HTTPException(status_code=409, detail="That user is already a member")
    except DuplicateInviteError:
        raise HTTPException(status_code=409, detail="That user already has a pending invite")
    return _to_invite_read(invite)


@router.get("/{room_id}/invites", response_model=list[InviteRead])
async def list_room_invites_endpoint(
    room_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_room_role(room_id, current_user, db, RoomRole.admin)
    invites = await list_room_invites(db, room_id)
    return [_to_invite_read(i) for i in invites]


@router.delete("/{room_id}/invites/{invite_id}", status_code=204)
async def revoke_invite_endpoint(
    room_id: uuid.UUID,
    invite_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_room_role(room_id, current_user, db, RoomRole.admin)
    try:
        await revoke_invite(db, room_id, invite_id)
    except InviteNotFoundError:
        raise HTTPException(status_code=404, detail="Invite not found")
    except InviteNotPendingError:
        raise HTTPException(status_code=400, detail="Invite is no longer pending")
