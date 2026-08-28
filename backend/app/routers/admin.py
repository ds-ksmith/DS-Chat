import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
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
from app.schemas.site_invite import SiteInviteCreate, SiteInviteRead
from app.schemas.smtp_settings import SmtpSettingsRead, SmtpSettingsUpdate
from app.schemas.upload_settings import UploadSettingsRead, UploadSettingsUpdate
from app.schemas.webhook import EventSubscriptionAdminRead, WebhookIncomingAdminRead
from app.services.admin_service import (
    CannotActOnSelfError,
    RoomNotFoundError,
    TargetNotRoomMemberError,
    UserNotFoundError,
    list_rooms_admin,
    list_users,
    reset_user_password,
    set_room_archived,
    set_user_active,
    set_user_site_admin,
    transfer_ownership_admin,
)
from app.services.audit import list_audit_log
from app.services.email_service import SmtpNotConfiguredError, send_test_email
from app.services.site_invite_service import (
    SiteInviteNotFoundError,
    SiteInviteNotPendingError,
    create_site_invite,
    list_site_invites,
    revoke_site_invite,
)
from app.services.smtp_settings_service import get_smtp_settings, upsert_smtp_settings
from app.services.upload_settings_service import get_upload_settings, update_upload_settings
from app.services.webhook_service import (
    list_all_event_subscriptions_admin,
    list_all_incoming_webhooks_admin,
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


@router.get("/webhooks/incoming", response_model=list[WebhookIncomingAdminRead])
async def list_incoming_webhooks_admin_endpoint(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_site_admin(current_user)
    webhooks = await list_all_incoming_webhooks_admin(db)
    return [
        WebhookIncomingAdminRead(
            id=w.id,
            room_id=w.room_id,
            token=w.token,
            created_by=w.created_by,
            description=w.description,
            created_at=w.created_at,
            room_name=w.room.name,
            created_by_username=w.creator.username,
        )
        for w in webhooks
    ]


@router.get("/event-subscriptions", response_model=list[EventSubscriptionAdminRead])
async def list_event_subscriptions_admin_endpoint(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_site_admin(current_user)
    subscriptions = await list_all_event_subscriptions_admin(db)
    return [
        EventSubscriptionAdminRead(
            id=s.id,
            room_id=s.room_id,
            event_types=s.event_types,
            target_url=s.target_url,
            created_by=s.created_by,
            created_at=s.created_at,
            room_name=s.room.name if s.room else None,
            created_by_username=s.creator.username,
        )
        for s in subscriptions
    ]


@router.post("/invites", response_model=SiteInviteRead, status_code=201)
async def create_site_invite_endpoint(
    data: SiteInviteCreate,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_site_admin(current_user)
    return await create_site_invite(db, current_user, str(request.base_url), data.email)


@router.get("/invites", response_model=list[SiteInviteRead])
async def list_site_invites_endpoint(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_site_admin(current_user)
    return await list_site_invites(db)


@router.delete("/invites/{invite_id}", response_model=SiteInviteRead)
async def revoke_site_invite_endpoint(
    invite_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_site_admin(current_user)
    try:
        return await revoke_site_invite(db, current_user, invite_id)
    except SiteInviteNotFoundError:
        raise HTTPException(status_code=404, detail="Invite not found")
    except SiteInviteNotPendingError:
        raise HTTPException(status_code=400, detail="Invite is no longer pending")


@router.get("/settings/smtp", response_model=SmtpSettingsRead | None)
async def get_smtp_settings_endpoint(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_site_admin(current_user)
    cfg = await get_smtp_settings(db)
    if cfg is None:
        return None
    return SmtpSettingsRead(
        host=cfg.host,
        port=cfg.port,
        username=cfg.username,
        has_password=bool(cfg.password_encrypted),
        from_address=cfg.from_address,
        use_tls=cfg.use_tls,
        updated_at=cfg.updated_at,
    )


@router.put("/settings/smtp", response_model=SmtpSettingsRead)
async def update_smtp_settings_endpoint(
    data: SmtpSettingsUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_site_admin(current_user)
    cfg = await upsert_smtp_settings(
        db,
        host=data.host,
        port=data.port,
        username=data.username,
        password=data.password,
        from_address=data.from_address,
        use_tls=data.use_tls,
    )
    return SmtpSettingsRead(
        host=cfg.host,
        port=cfg.port,
        username=cfg.username,
        has_password=bool(cfg.password_encrypted),
        from_address=cfg.from_address,
        use_tls=cfg.use_tls,
        updated_at=cfg.updated_at,
    )


@router.post("/settings/smtp/test", status_code=204)
async def test_smtp_settings_endpoint(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_site_admin(current_user)
    try:
        await send_test_email(db, current_user.email, theme_user=current_user)
    except SmtpNotConfiguredError:
        raise HTTPException(status_code=400, detail="SMTP is not configured yet")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to send test email: {exc}")


@router.get("/settings/uploads", response_model=UploadSettingsRead)
async def get_upload_settings_endpoint(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_site_admin(current_user)
    cfg = await get_upload_settings(db)
    return UploadSettingsRead(max_upload_bytes=cfg.max_upload_bytes, updated_at=cfg.updated_at)


@router.put("/settings/uploads", response_model=UploadSettingsRead)
async def update_upload_settings_endpoint(
    data: UploadSettingsUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_site_admin(current_user)
    cfg = await update_upload_settings(db, max_upload_bytes=data.max_upload_bytes)
    return UploadSettingsRead(max_upload_bytes=cfg.max_upload_bytes, updated_at=cfg.updated_at)
