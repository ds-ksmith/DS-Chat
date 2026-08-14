import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user, require_site_admin
from app.models import User
from app.schemas.bot import ApiTokenCreate, ApiTokenCreated, ApiTokenRead, BotCreate, BotRead
from app.services.bot_service import (
    BotNotFoundError,
    DuplicateBotError,
    InvalidScopeError,
    TokenNotFoundError,
    create_api_token,
    create_bot,
    list_api_tokens,
    list_bots,
    revoke_api_token,
)

router = APIRouter(prefix="/api/admin/bots", tags=["bots"])


@router.post("", response_model=BotRead, status_code=201)
async def create_bot_endpoint(
    data: BotCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_site_admin(current_user)
    try:
        return await create_bot(db, current_user, data.username)
    except DuplicateBotError:
        raise HTTPException(status_code=409, detail="A user with this username already exists")


@router.get("", response_model=list[BotRead])
async def list_bots_endpoint(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_site_admin(current_user)
    return await list_bots(db)


@router.post("/{bot_id}/tokens", response_model=ApiTokenCreated, status_code=201)
async def create_token_endpoint(
    bot_id: uuid.UUID,
    data: ApiTokenCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_site_admin(current_user)
    try:
        token, plaintext = await create_api_token(db, current_user, bot_id, data.scopes)
    except BotNotFoundError:
        raise HTTPException(status_code=404, detail="Bot not found")
    except InvalidScopeError:
        raise HTTPException(status_code=400, detail="Unrecognized scope")
    return ApiTokenCreated(
        id=token.id,
        owner_id=token.owner_id,
        scopes=token.scopes,
        last_used_at=token.last_used_at,
        created_at=token.created_at,
        token=plaintext,
    )


@router.get("/{bot_id}/tokens", response_model=list[ApiTokenRead])
async def list_tokens_endpoint(
    bot_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_site_admin(current_user)
    return await list_api_tokens(db, bot_id)


@router.delete("/tokens/{token_id}", status_code=204)
async def revoke_token_endpoint(
    token_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_site_admin(current_user)
    try:
        await revoke_api_token(db, current_user, token_id)
    except TokenNotFoundError:
        raise HTTPException(status_code=404, detail="Token not found")
