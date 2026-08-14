import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models import User
from app.schemas.invite import InviteRead
from app.schemas.room import RoomMemberRead
from app.services.invite_service import (
    InviteExpiredError,
    InviteNotFoundError,
    InviteNotPendingError,
    WrongInviteTargetError,
    accept_invite,
    decline_invite,
    list_my_invites,
)

router = APIRouter(prefix="/api/invites", tags=["invites"])


@router.get("/mine", response_model=list[InviteRead])
async def list_my_invites_endpoint(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await list_my_invites(db, current_user.id)


@router.post("/{invite_id}/accept", response_model=RoomMemberRead)
async def accept_invite_endpoint(
    invite_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        membership = await accept_invite(db, invite_id, current_user.id)
    except InviteNotFoundError:
        raise HTTPException(status_code=404, detail="Invite not found")
    except WrongInviteTargetError:
        raise HTTPException(status_code=403, detail="This invite is not addressed to you")
    except InviteNotPendingError:
        raise HTTPException(status_code=400, detail="Invite is no longer pending")
    except InviteExpiredError:
        raise HTTPException(status_code=400, detail="Invite has expired")

    return RoomMemberRead(
        user_id=membership.user_id,
        username=current_user.username,
        role=membership.role,
        joined_at=membership.joined_at,
    )


@router.post("/{invite_id}/decline", response_model=InviteRead)
async def decline_invite_endpoint(
    invite_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await decline_invite(db, invite_id, current_user.id)
    except InviteNotFoundError:
        raise HTTPException(status_code=404, detail="Invite not found")
    except WrongInviteTargetError:
        raise HTTPException(status_code=403, detail="This invite is not addressed to you")
    except InviteNotPendingError:
        raise HTTPException(status_code=400, detail="Invite is no longer pending")
