import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models import User
from app.schemas.user import UserDirectoryRead
from app.storage import UPLOADS_DIR

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("", response_model=list[UserDirectoryRead])
async def list_users_directory_endpoint(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(User)
        .where(User.is_active.is_(True), User.is_bot.is_(False))
        .order_by(User.username)
    )
    return list(result.scalars().all())


@router.get("/{user_id}/avatar")
async def get_user_avatar_endpoint(
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user = await db.get(User, user_id)
    if user is None or not user.avatar_filename:
        raise HTTPException(status_code=404, detail="No avatar set")
    return FileResponse(
        UPLOADS_DIR / user.avatar_filename,
        media_type=user.avatar_content_type,
        # Unlike message images (content-addressed, immutable once posted),
        # an avatar URL is identity-addressed and its content can change on
        # re-upload -- a short cache instead of `immutable` so a stale copy
        # doesn't linger. Not room-membership-gated: avatar visibility
        # matches username visibility (anyone logged in), unlike room-scoped
        # message content.
        headers={"Cache-Control": "private, max-age=300"},
    )
