import uuid

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import RoomMembership, RoomRole, User

_ROLE_RANK = {RoomRole.member: 0, RoomRole.admin: 1, RoomRole.owner: 2}


async def get_current_user(
    request: Request, db: AsyncSession = Depends(get_db)
) -> User:
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    user = await db.get(User, uuid.UUID(user_id))
    if user is None or not user.is_active:
        request.session.clear()
        raise HTTPException(status_code=401, detail="Not authenticated")

    return user


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
