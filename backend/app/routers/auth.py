from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models import User
from app.schemas.auth import LoginRequest
from app.schemas.user import ProfileUpdate, UserRead
from app.services.auth_service import (
    AccountDeactivatedError,
    InvalidCredentialsError,
    authenticate_user,
)
from app.storage import (
    ALLOWED_IMAGE_CONTENT_TYPES,
    ImageTooLargeError,
    InvalidImageError,
    delete_image,
    process_image,
    read_capped,
    save_image,
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
    display_name = data.display_name.strip() if data.display_name else None
    current_user.display_name = display_name or None
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

    try:
        data = await read_capped(file)
    except ImageTooLargeError:
        raise HTTPException(status_code=413, detail="Image exceeds 8 MB limit")

    try:
        data, ext = process_image(
            data, file.content_type, square=True, max_dimension=AVATAR_MAX_DIMENSION
        )
    except InvalidImageError:
        raise HTTPException(status_code=400, detail="File is not a valid image")

    previous_filename = current_user.avatar_filename
    storage_filename = save_image(data, ext)
    current_user.avatar_filename = storage_filename
    current_user.avatar_content_type = file.content_type
    await db.commit()
    await db.refresh(current_user)

    if previous_filename:
        delete_image(previous_filename)

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
        delete_image(previous_filename)

    return current_user
