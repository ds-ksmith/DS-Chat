from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.site_invite import SignupComplete, SignupValidateRead
from app.schemas.user import UserRead
from app.services.auth_service import DuplicateUserError
from app.services.site_invite_service import (
    SiteInviteInvalidError,
    complete_signup,
    validate_signup_token,
)

router = APIRouter(prefix="/api/signup", tags=["signup"])


@router.get("/validate", response_model=SignupValidateRead)
async def validate_signup_endpoint(
    token: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    try:
        invite = await validate_signup_token(db, token)
    except SiteInviteInvalidError:
        raise HTTPException(status_code=400, detail="This invite link is invalid or has expired")
    return SignupValidateRead(email=invite.email)


@router.post("", response_model=UserRead)
async def complete_signup_endpoint(
    data: SignupComplete,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    try:
        user = await complete_signup(db, data.token, data.username, data.password)
    except SiteInviteInvalidError:
        raise HTTPException(status_code=400, detail="This invite link is invalid or has expired")
    except DuplicateUserError:
        raise HTTPException(status_code=409, detail="That username or email is already taken")

    request.session["user_id"] = str(user.id)
    return user
