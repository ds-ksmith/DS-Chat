import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, Response, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.dependencies import get_current_user
from app.models import User
from app.schemas.auth import LoginRequest
from app.schemas.password import ForgotPasswordRequest, PasswordChange, ResetPasswordComplete
from app.schemas.session import SessionRead
from app.schemas.user import ProfileUpdate, UserRead
from app.services.auth_service import (
    AccountDeactivatedError,
    InvalidCredentialsError,
    authenticate_user,
)
from app.services.message_events import broadcast_member_updated
from app.services.password_service import (
    InvalidCurrentPasswordError,
    PasswordResetInvalidError,
    change_password,
    complete_password_reset,
    request_password_reset,
    validate_reset_token,
)
from app.services.session_service import (
    SessionNotFoundError,
    list_sessions,
    revoke_session,
    revoke_session_unchecked,
    start_session,
)
from app.services.upload_settings_service import format_mb, get_upload_settings
from app.services.user_agent_service import describe_user_agent
from app.storage import (
    ALLOWED_IMAGE_CONTENT_TYPES,
    InvalidImageError,
    UploadTooLargeError,
    delete_file,
    process_image,
    read_capped,
    save_file,
)

AVATAR_MAX_DIMENSION = 512

# No POST /register here: this is an invite-only site. Accounts are created
# by an operator via `python -m app.cli create-user` (see app/cli.py), not
# through a public endpoint.

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=UserRead)
async def login(
    request: Request, data: LoginRequest, db: AsyncSession = Depends(get_db)
) -> User:
    try:
        user = await authenticate_user(
            db, data.username_or_email, data.password
        )
    except InvalidCredentialsError:
        raise HTTPException(status_code=401, detail="Invalid username/email or password")
    except AccountDeactivatedError:
        raise HTTPException(status_code=401, detail="Account is deactivated")

    await start_session(request, db, user.id)
    return user


@router.post("/logout", status_code=204)
async def logout(request: Request, db: AsyncSession = Depends(get_db)) -> Response:
    session_id = request.session.get("session_id")
    if session_id:
        await revoke_session_unchecked(db, uuid.UUID(session_id))
    request.session.clear()
    return Response(status_code=204)


@router.get("/me", response_model=UserRead)
async def me(current_user: User = Depends(get_current_user)) -> User:
    return current_user


@router.patch("/me", response_model=UserRead)
async def update_profile(
    request: Request,
    data: ProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    # Only apply fields actually present in the request body -- a call that
    # only wants to change the theme must not clobber display_name back to
    # None, and vice versa.
    updates = data.model_dump(exclude_unset=True)
    if "display_name" in updates:
        display_name = updates["display_name"].strip() if updates["display_name"] else None
        current_user.display_name = display_name or None
    if "theme" in updates:
        current_user.theme = updates["theme"]
    if "text_scale" in updates:
        current_user.text_scale = updates["text_scale"]
    if "emoji_scale" in updates:
        current_user.emoji_scale = updates["emoji_scale"]
    if "appear_offline" in updates:
        current_user.appear_offline = updates["appear_offline"]
    await db.commit()
    # A plain db.refresh() would expire (and, on next access, lazily
    # reload) the active_custom_theme relationship get_current_user
    # eager-loaded -- not safe in an async session. Re-fetching with the
    # same eager-load instead of refreshing avoids that entirely.
    current_user = await db.get(
        User, current_user.id, options=[selectinload(User.active_custom_theme)]
    )
    # theme is private to this user, not shown to anyone else -- only
    # broadcast when something other members would actually see changed.
    if "display_name" in updates or "appear_offline" in updates:
        await broadcast_member_updated(db, request.app.state.broadcaster, current_user.id)
    return current_user


@router.post("/me/avatar", response_model=UserRead)
async def upload_avatar(
    request: Request,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    if file.content_type not in ALLOWED_IMAGE_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail="Unsupported image type")

    upload_settings = await get_upload_settings(db)
    try:
        data = await read_capped(file, cap=upload_settings.max_upload_bytes)
    except UploadTooLargeError:
        raise HTTPException(
            status_code=413,
            detail=f"Image exceeds {format_mb(upload_settings.max_upload_bytes)} limit",
        )

    try:
        data, ext = process_image(
            data, file.content_type, square=True, max_dimension=AVATAR_MAX_DIMENSION
        )
    except InvalidImageError:
        raise HTTPException(status_code=400, detail="File is not a valid image")

    previous_filename = current_user.avatar_filename
    storage_filename = save_file(data, ext)
    current_user.avatar_filename = storage_filename
    current_user.avatar_content_type = file.content_type
    await db.commit()
    # See update_profile's comment -- refresh() would expire the eager-
    # loaded active_custom_theme relationship instead of preserving it.
    current_user = await db.get(
        User, current_user.id, options=[selectinload(User.active_custom_theme)]
    )

    if previous_filename:
        delete_file(previous_filename)

    await broadcast_member_updated(db, request.app.state.broadcaster, current_user.id)
    return current_user


@router.delete("/me/avatar", response_model=UserRead)
async def remove_avatar(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    previous_filename = current_user.avatar_filename
    current_user.avatar_filename = None
    current_user.avatar_content_type = None
    await db.commit()
    # See update_profile's comment -- refresh() would expire the eager-
    # loaded active_custom_theme relationship instead of preserving it.
    current_user = await db.get(
        User, current_user.id, options=[selectinload(User.active_custom_theme)]
    )

    if previous_filename:
        delete_file(previous_filename)

    await broadcast_member_updated(db, request.app.state.broadcaster, current_user.id)
    return current_user


@router.patch("/password", status_code=204)
async def change_password_endpoint(
    data: PasswordChange,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    try:
        await change_password(db, current_user, data.current_password, data.new_password)
    except InvalidCurrentPasswordError:
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    return Response(status_code=204)


@router.post("/forgot-password", status_code=204)
async def forgot_password_endpoint(
    data: ForgotPasswordRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Response:
    # Always 204, whether or not the email matched an account -- the
    # response must not reveal which emails are registered.
    await request_password_reset(db, data.email, str(request.base_url))
    return Response(status_code=204)


@router.get("/reset-password/validate", status_code=204)
async def validate_reset_password_endpoint(
    token: str = Query(...),
    db: AsyncSession = Depends(get_db),
) -> Response:
    try:
        await validate_reset_token(db, token)
    except PasswordResetInvalidError:
        raise HTTPException(status_code=400, detail="This reset link is invalid or has expired")
    return Response(status_code=204)


@router.post("/reset-password", response_model=UserRead)
async def complete_reset_password_endpoint(
    data: ResetPasswordComplete,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User:
    try:
        user = await complete_password_reset(db, data.token, data.new_password)
    except PasswordResetInvalidError:
        raise HTTPException(status_code=400, detail="This reset link is invalid or has expired")

    await start_session(request, db, user.id)
    return user


@router.get("/sessions", response_model=list[SessionRead])
async def list_sessions_endpoint(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    sessions = await list_sessions(db, current_user.id)
    return [
        SessionRead(
            id=s.id,
            ip_address=s.ip_address,
            device_label=describe_user_agent(s.user_agent),
            created_at=s.created_at,
            last_seen_at=s.last_seen_at,
            is_current=s.id == request.state.session_id,
        )
        for s in sessions
    ]


@router.delete("/sessions/{session_id}", status_code=204)
async def revoke_session_endpoint(
    session_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await revoke_session(db, current_user.id, session_id)
    except SessionNotFoundError:
        raise HTTPException(status_code=404, detail="Session not found")
