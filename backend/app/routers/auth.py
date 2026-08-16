from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, Response, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models import User
from app.schemas.auth import LoginRequest
from app.schemas.password import ForgotPasswordRequest, PasswordChange, ResetPasswordComplete
from app.schemas.user import ProfileUpdate, UserRead
from app.services.auth_service import (
    AccountDeactivatedError,
    InvalidCredentialsError,
    authenticate_user,
)
from app.services.password_service import (
    InvalidCurrentPasswordError,
    PasswordResetInvalidError,
    change_password,
    complete_password_reset,
    request_password_reset,
    validate_reset_token,
)
from app.services.upload_settings_service import format_mb, get_upload_settings
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

    request.session["user_id"] = str(user.id)
    return user


@router.post("/logout", status_code=204)
async def logout(request: Request) -> Response:
    request.session.clear()
    return Response(status_code=204)


@router.get("/me", response_model=UserRead)
async def me(current_user: User = Depends(get_current_user)) -> User:
    return current_user


@router.patch("/me", response_model=UserRead)
async def update_profile(
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
    await db.commit()
    await db.refresh(current_user)
    return current_user


@router.post("/me/avatar", response_model=UserRead)
async def upload_avatar(
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
    await db.refresh(current_user)

    if previous_filename:
        delete_file(previous_filename)

    return current_user


@router.delete("/me/avatar", response_model=UserRead)
async def remove_avatar(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    previous_filename = current_user.avatar_filename
    current_user.avatar_filename = None
    current_user.avatar_content_type = None
    await db.commit()
    await db.refresh(current_user)

    if previous_filename:
        delete_file(previous_filename)

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

    request.session["user_id"] = str(user.id)
    return user
