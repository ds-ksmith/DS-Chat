import uuid

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.dependencies import get_current_user
from app.models import User
from app.schemas.custom_theme import CustomThemeCreate, CustomThemeRead, CustomThemeUpdate
from app.schemas.user import UserRead
from app.services.custom_theme_service import (
    CustomThemeLimitReachedError,
    CustomThemeNotFoundError,
    activate_custom_theme,
    create_custom_theme,
    delete_custom_theme,
    list_custom_themes,
    update_custom_theme,
)

router = APIRouter(prefix="/api/custom-themes", tags=["custom-themes"])


@router.get("", response_model=list[CustomThemeRead])
async def list_custom_themes_endpoint(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await list_custom_themes(db, current_user.id)


@router.post("", response_model=CustomThemeRead, status_code=201)
async def create_custom_theme_endpoint(
    data: CustomThemeCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await create_custom_theme(db, current_user.id, data.name, data.colors)
    except CustomThemeLimitReachedError:
        raise HTTPException(status_code=400, detail="Custom theme limit reached")


@router.patch("/{theme_id}", response_model=CustomThemeRead)
async def update_custom_theme_endpoint(
    theme_id: uuid.UUID,
    data: CustomThemeUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await update_custom_theme(db, current_user.id, theme_id, data.name, data.colors)
    except CustomThemeNotFoundError:
        raise HTTPException(status_code=404, detail="Custom theme not found")


@router.delete("/{theme_id}", status_code=204)
async def delete_custom_theme_endpoint(
    theme_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await delete_custom_theme(db, current_user.id, theme_id)
    except CustomThemeNotFoundError:
        raise HTTPException(status_code=404, detail="Custom theme not found")
    return Response(status_code=204)


@router.post("/{theme_id}/activate", response_model=UserRead)
async def activate_custom_theme_endpoint(
    theme_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await activate_custom_theme(db, current_user.id, theme_id)
    except CustomThemeNotFoundError:
        raise HTTPException(status_code=404, detail="Custom theme not found")
    # Re-fetch with the eager-load UserRead.active_custom_theme needs --
    # current_user itself is stale (activate_custom_theme mutated a
    # different Python object fetched inside the service call).
    return await db.get(
        User, current_user.id, options=[selectinload(User.active_custom_theme)]
    )
