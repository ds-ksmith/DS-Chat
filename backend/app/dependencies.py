import uuid

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models import RoomMembership, RoomRole, User
from app.services.bot_service import resolve_token

_ROLE_RANK = {RoomRole.member: 0, RoomRole.admin: 1, RoomRole.owner: 2}


async def get_current_user(
    request: Request, db: AsyncSession = Depends(get_db)
) -> User:
    # Bearer token (bots) takes priority over the session cookie (humans) --
    # a request either carries one or the other, never meaningfully both.
    # Downstream, a token-authenticated bot is subject to the exact same
    # room-membership/role checks as a session-authenticated human; the
    # token additionally narrows what it can do via require_scope below.
    auth_header = request.headers.get("authorization")
    if auth_header and auth_header.lower().startswith("bearer "):
        resolved = await resolve_token(db, auth_header[len("bearer ") :].strip())
        if resolved is None:
            raise HTTPException(status_code=401, detail="Invalid or revoked API token")
        user, token = resolved
        request.state.api_token = token
        return user

    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    # Eager-loaded so UserRead.active_custom_theme (app/schemas/user.py) can
    # be read without a MissingGreenlet -- selectinload skips the second
    # query entirely when active_custom_theme_id is null (the common case),
    # so this costs nothing for users who've never set a custom theme.
    user = await db.get(
        User, uuid.UUID(user_id), options=[selectinload(User.active_custom_theme)]
    )
    if user is None or not user.is_active:
        request.session.clear()
        raise HTTPException(status_code=401, detail="Not authenticated")

    return user


def require_scope(request: Request, scope: str) -> None:
    token = getattr(request.state, "api_token", None)
    if token is not None and scope not in token.scopes:
        raise HTTPException(status_code=403, detail=f"Token missing required scope: {scope}")


async def require_room_member(
    room_id: uuid.UUID, user: User, db: AsyncSession
) -> RoomMembership:
    result = await db.execute(
        select(RoomMembership).where(
            RoomMembership.room_id == room_id, RoomMembership.user_id == user.id
        )
    )
    membership = result.scalar_one_or_none()
    if membership is None:
        raise HTTPException(status_code=403, detail="Not a member of this room")
    return membership


async def require_room_role(
    room_id: uuid.UUID, user: User, db: AsyncSession, minimum: RoomRole
) -> RoomMembership:
    membership = await require_room_member(room_id, user, db)
    if _ROLE_RANK[membership.role] < _ROLE_RANK[minimum]:
        raise HTTPException(status_code=403, detail="Insufficient room role")
    return membership


def require_site_admin(user: User) -> None:
    if not user.is_site_admin:
        raise HTTPException(status_code=403, detail="Site admin required")
