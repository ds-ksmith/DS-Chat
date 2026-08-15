import pathlib
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import (
    get_current_user,
    require_room_member,
    require_room_role,
    require_scope,
)
from app.models import MessageFile, MessageImage, RoomRole, User
from app.schemas.message import MessageFileInfo, MessageRead
from app.schemas.message_file import MessageFileCreated
from app.schemas.message_image import MessageImageCreated
from app.schemas.room import (
    MyRoomItem,
    RoomCreate,
    RoomListItem,
    RoomMemberAdd,
    RoomMemberRead,
    RoomMemberRoleUpdate,
    RoomRead,
    RoomUpdate,
    TransferOwnershipRequest,
)
from app.schemas.webhook import (
    EventSubscriptionCreate,
    EventSubscriptionCreated,
    EventSubscriptionRead,
    WebhookIncomingCreate,
    WebhookIncomingRead,
)
from app.services.message_service import get_reactions_for_messages, list_recent_messages
from app.services.room_service import (
    AlreadyMemberError,
    CannotRemoveOwnerError,
    DuplicateRoomError,
    InsufficientRoleError,
    MembershipNotFoundError,
    OwnerMustTransferError,
    RoomIsPrivateError,
    RoomNotFoundError,
    TargetUserNotFoundError,
    add_member,
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
from app.services.webhook_service import (
    InvalidEventTypeError,
    SubscriptionNotFoundError,
    WebhookNotFoundError,
    create_event_subscription,
    create_incoming_webhook,
    list_event_subscriptions,
    list_incoming_webhooks,
    revoke_event_subscription,
    revoke_incoming_webhook,
)
from app.services.ssrf import UnsafeWebhookUrlError
from app.storage import (
    ALLOWED_IMAGE_CONTENT_TYPES,
    MAX_FILE_BYTES,
    UPLOADS_DIR,
    InvalidImageError,
    UploadTooLargeError,
    process_image,
    read_capped,
    save_file,
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
            user_id=m.user_id,
            username=m.user.username,
            display_name=m.user.display_name,
            avatar_filename=m.user.avatar_filename,
            role=m.role,
            joined_at=m.joined_at,
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
        display_name=membership.user.display_name,
        avatar_filename=membership.user.avatar_filename,
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


def _to_message_file_info(file: MessageFile) -> MessageFileInfo:
    return MessageFileInfo(
        id=file.id,
        filename=file.original_filename,
        size_bytes=file.size_bytes,
        content_type=file.content_type,
    )


@router.get("/{room_id}/messages", response_model=list[MessageRead])
async def get_room_messages_endpoint(
    room_id: uuid.UUID,
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_scope(request, "read:messages")
    await require_room_member(room_id, current_user, db)
    messages = await list_recent_messages(db, room_id, limit)
    reactions_by_message = await get_reactions_for_messages(db, [m.id for m in messages])
    return [
        MessageRead(
            id=m.id,
            room_id=m.room_id,
            user_id=m.user_id,
            username=m.user.username,
            content=m.content,
            image_id=m.image_id,
            file=_to_message_file_info(m.file) if m.file else None,
            reactions=reactions_by_message.get(m.id, []),
            created_at=m.created_at,
            edited_at=m.edited_at,
        )
        for m in messages
    ]


@router.post("/{room_id}/images", response_model=MessageImageCreated, status_code=201)
async def upload_room_image_endpoint(
    room_id: uuid.UUID,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_room_member(room_id, current_user, db)

    if file.content_type not in ALLOWED_IMAGE_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail="Unsupported image type")

    try:
        data = await read_capped(file)
    except UploadTooLargeError:
        raise HTTPException(status_code=413, detail="Image exceeds 8 MB limit")

    try:
        data, ext = process_image(data, file.content_type)
    except InvalidImageError:
        raise HTTPException(status_code=400, detail="File is not a valid image")

    storage_filename = save_file(data, ext)
    image = MessageImage(
        room_id=room_id,
        uploaded_by=current_user.id,
        storage_filename=storage_filename,
        content_type=file.content_type,
        size_bytes=len(data),
    )
    db.add(image)
    await db.commit()
    await db.refresh(image)
    return MessageImageCreated(id=image.id)


@router.get("/{room_id}/images/{image_id}")
async def get_room_image_endpoint(
    room_id: uuid.UUID,
    image_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_room_member(room_id, current_user, db)
    image = await db.get(MessageImage, image_id)
    if image is None or image.room_id != room_id:
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(
        UPLOADS_DIR / image.storage_filename,
        media_type=image.content_type,
        headers={"Cache-Control": "private, max-age=31536000, immutable"},
    )


@router.post("/{room_id}/files", response_model=MessageFileCreated, status_code=201)
async def upload_room_file_endpoint(
    room_id: uuid.UUID,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_room_member(room_id, current_user, db)

    try:
        data = await read_capped(file, cap=MAX_FILE_BYTES)
    except UploadTooLargeError:
        raise HTTPException(status_code=413, detail="File exceeds 8 MB limit")

    original_filename = file.filename or "file"
    ext = pathlib.Path(original_filename).suffix
    storage_filename = save_file(data, ext)
    message_file = MessageFile(
        room_id=room_id,
        uploaded_by=current_user.id,
        storage_filename=storage_filename,
        original_filename=original_filename,
        content_type=file.content_type or "application/octet-stream",
        size_bytes=len(data),
    )
    db.add(message_file)
    await db.commit()
    await db.refresh(message_file)
    return MessageFileCreated(
        id=message_file.id,
        filename=message_file.original_filename,
        size_bytes=message_file.size_bytes,
        content_type=message_file.content_type,
    )


@router.get("/{room_id}/files/{file_id}")
async def get_room_file_endpoint(
    room_id: uuid.UUID,
    file_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_room_member(room_id, current_user, db)
    message_file = await db.get(MessageFile, file_id)
    if message_file is None or message_file.room_id != room_id:
        raise HTTPException(status_code=404, detail="File not found")
    # `filename=` makes Starlette set Content-Disposition: attachment,
    # forcing a download instead of an inline render regardless of
    # content-type -- the mitigation for a same-origin-served, user-
    # uploaded file (e.g. .html/.svg) executing script in this app's own
    # origin if opened directly. No content-type allowlist needed on top
    # of this; see backend/README.md.
    return FileResponse(
        UPLOADS_DIR / message_file.storage_filename,
        media_type=message_file.content_type,
        filename=message_file.original_filename,
        headers={"Cache-Control": "private, max-age=31536000, immutable"},
    )


@router.post("/{room_id}/members", response_model=RoomMemberRead, status_code=201)
async def add_member_endpoint(
    room_id: uuid.UUID,
    data: RoomMemberAdd,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        room = await get_room(db, room_id)
        await require_room_role(room_id, current_user, db, RoomRole.admin)
        membership = await add_member(db, room, data.user_id, str(request.base_url))
    except RoomNotFoundError:
        raise HTTPException(status_code=404, detail="Room not found")
    except TargetUserNotFoundError:
        raise HTTPException(status_code=404, detail="No user with that ID")
    except AlreadyMemberError:
        raise HTTPException(status_code=409, detail="That user is already a member")
    return RoomMemberRead(
        user_id=membership.user_id,
        username=membership.user.username,
        display_name=membership.user.display_name,
        avatar_filename=membership.user.avatar_filename,
        role=membership.role,
        joined_at=membership.joined_at,
    )


@router.post("/{room_id}/webhooks/incoming", response_model=WebhookIncomingRead, status_code=201)
async def create_incoming_webhook_endpoint(
    room_id: uuid.UUID,
    data: WebhookIncomingCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_room_role(room_id, current_user, db, RoomRole.admin)
    return await create_incoming_webhook(db, current_user, room_id, data.description)


@router.get("/{room_id}/webhooks/incoming", response_model=list[WebhookIncomingRead])
async def list_incoming_webhooks_endpoint(
    room_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_room_role(room_id, current_user, db, RoomRole.admin)
    return await list_incoming_webhooks(db, room_id)


@router.delete("/{room_id}/webhooks/incoming/{webhook_id}", status_code=204)
async def revoke_incoming_webhook_endpoint(
    room_id: uuid.UUID,
    webhook_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_room_role(room_id, current_user, db, RoomRole.admin)
    try:
        await revoke_incoming_webhook(db, room_id, webhook_id)
    except WebhookNotFoundError:
        raise HTTPException(status_code=404, detail="Webhook not found")


@router.post(
    "/{room_id}/event-subscriptions", response_model=EventSubscriptionCreated, status_code=201
)
async def create_event_subscription_endpoint(
    room_id: uuid.UUID,
    data: EventSubscriptionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_room_role(room_id, current_user, db, RoomRole.admin)
    try:
        subscription, secret = await create_event_subscription(
            db, current_user, room_id, data.event_types, data.target_url
        )
    except InvalidEventTypeError:
        raise HTTPException(status_code=400, detail="Unrecognized event type")
    except UnsafeWebhookUrlError:
        raise HTTPException(
            status_code=400, detail="target_url is not allowed (internal/private address)"
        )
    return EventSubscriptionCreated(
        id=subscription.id,
        room_id=subscription.room_id,
        event_types=subscription.event_types,
        target_url=subscription.target_url,
        created_by=subscription.created_by,
        created_at=subscription.created_at,
        signing_secret=secret,
    )


@router.get("/{room_id}/event-subscriptions", response_model=list[EventSubscriptionRead])
async def list_event_subscriptions_endpoint(
    room_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_room_role(room_id, current_user, db, RoomRole.admin)
    return await list_event_subscriptions(db, room_id)


@router.delete("/{room_id}/event-subscriptions/{subscription_id}", status_code=204)
async def revoke_event_subscription_endpoint(
    room_id: uuid.UUID,
    subscription_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_room_role(room_id, current_user, db, RoomRole.admin)
    try:
        await revoke_event_subscription(db, room_id, subscription_id)
    except SubscriptionNotFoundError:
        raise HTTPException(status_code=404, detail="Event subscription not found")
