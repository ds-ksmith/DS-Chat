import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user, require_site_admin
from app.models import Room, RoomMembership, User
from app.schemas.admin import (
    AdminRoomRead,
    AdminUserRead,
    AuditLogEntryRead,
    ResetPasswordRequest,
    TransferOwnershipRequest,
)
from app.services.admin_service import (
    CannotActOnSelfError,
    RoomNotFoundError,
    TargetNotRoomMemberError,
    UserNotFoundError,
    list_audit_log,
    list_rooms_admin,
    list_users,
    reset_user_password,
    set_room_archived,
    set_user_active,
    set_user_site_admin,
    transfer_ownership_admin,
)

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/users", response_model=list[AdminUserRead])
async def list_users_endpoint(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_site_admin(current_user)
    return await list_users(db)


@router.post("/users/{user_id}/deactivate", response_model=AdminUserRead)
async def deactivate_user_endpoint(
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_site_admin(current_user)
    try:
        return await set_user_active(db, current_user, user_id, active=False)
    except CannotActOnSelfError:
        raise HTTPException(status_code=400, detail="Cannot deactivate your own account")
    except UserNotFoundError:
        raise HTTPException(status_code=404, detail="User not found")


@router.post("/users/{user_id}/reactivate", response_model=AdminUserRead)
async def reactivate_user_endpoint(
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_site_admin(current_user)
    try:
        return await set_user_active(db, current_user, user_id, active=True)
    except CannotActOnSelfError:
        raise HTTPException(status_code=400, detail="Cannot reactivate your own account")
    except UserNotFoundError:
        raise HTTPException(status_code=404, detail="User not found")


@router.post("/users/{user_id}/reset-password", status_code=204)
async def reset_user_password_endpoint(
    user_id: uuid.UUID,
    data: ResetPasswordRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_site_admin(current_user)
    try:
        await reset_user_password(db, current_user, user_id, data.new_password)
    except UserNotFoundError:
        raise HTTPException(status_code=404, detail="User not found")


@router.post("/users/{user_id}/promote", response_model=AdminUserRead)
async def promote_user_endpoint(
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_site_admin(current_user)
    try:
        return await set_user_site_admin(db, current_user, user_id, is_admin=True)
    except CannotActOnSelfError:
        raise HTTPException(status_code=400, detail="Cannot promote your own account")
    except UserNotFoundError:
        raise HTTPException(status_code=404, detail="User not found")


@router.post("/users/{user_id}/demote", response_model=AdminUserRead)
async def demote_user_endpoint(
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_site_admin(current_user)
    try:
        return await set_user_site_admin(db, current_user, user_id, is_admin=False)
    except CannotActOnSelfError:
        raise HTTPException(status_code=400, detail="Cannot demote your own account")
    except UserNotFoundError:
        raise HTTPException(status_code=404, detail="User not found")


@router.get("/rooms", response_model=list[AdminRoomRead])
async def list_rooms_endpoint(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_site_admin(current_user)
    rooms = await list_rooms_admin(db)
    return [
        AdminRoomRead(
            id=room.id,
            name=room.name,
            description=room.description,
            is_private=room.is_private,
            is_archived=room.is_archived,
            owner_id=room.owner_id,
            created_at=room.created_at,
            member_count=member_count,
        )
        for room, member_count in rooms
    ]


@router.post("/rooms/{room_id}/archive", response_model=AdminRoomRead)
async def archive_room_endpoint(
    room_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_site_admin(current_user)
    try:
        room = await set_room_archived(db, current_user, room_id, archived=True)
    except RoomNotFoundError:
        raise HTTPException(status_code=404, detail="Room not found")
    return await _to_admin_room_read(db, room)


@router.post("/rooms/{room_id}/unarchive", response_model=AdminRoomRead)
async def unarchive_room_endpoint(
    room_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_site_admin(current_user)
    try:
        room = await set_room_archived(db, current_user, room_id, archived=False)
    except RoomNotFoundError:
        raise HTTPException(status_code=404, detail="Room not found")
    return await _to_admin_room_read(db, room)


@router.post("/rooms/{room_id}/transfer-ownership", response_model=AdminRoomRead)
async def transfer_ownership_endpoint(
    room_id: uuid.UUID,
    data: TransferOwnershipRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_site_admin(current_user)
    try:
        room = await transfer_ownership_admin(db, current_user, room_id, data.new_owner_id)
    except RoomNotFoundError:
        raise HTTPException(status_code=404, detail="Room not found")
    except TargetNotRoomMemberError:
        raise HTTPException(
            status_code=400, detail="New owner must already be a member of the room"
        )
    return await _to_admin_room_read(db, room)


async def _to_admin_room_read(db: AsyncSession, room: Room) -> AdminRoomRead:
    result = await db.execute(
        select(func.count()).select_from(RoomMembership).where(RoomMembership.room_id == room.id)
    )
    member_count = result.scalar_one()
    return AdminRoomRead(
        id=room.id,
        name=room.name,
        description=room.description,
        is_private=room.is_private,
        is_archived=room.is_archived,
        owner_id=room.owner_id,
        created_at=room.created_at,
        member_count=member_count,
    )


@router.get("/audit-log", response_model=list[AuditLogEntryRead])
async def list_audit_log_endpoint(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_site_admin(current_user)
    entries = await list_audit_log(db, limit=limit, offset=offset)
    return [
        AuditLogEntryRead(
            id=e.id,
            actor_id=e.actor_id,
            actor_username=e.actor.username,
            action=e.action,
            target_type=e.target_type,
            target_id=e.target_id,
            metadata=e.metadata_,
            created_at=e.created_at,
        )
        for e in entries
    ]
