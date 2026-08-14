from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models import User
from app.schemas.auth import LoginRequest
from app.schemas.user import UserRead
from app.services.auth_service import InvalidCredentialsError, authenticate_user

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

    request.session["user_id"] = str(user.id)
    return user


@router.post("/logout", status_code=204)
async def logout(request: Request) -> Response:
    request.session.clear()
    return Response(status_code=204)


@router.get("/me", response_model=UserRead)
async def me(current_user: User = Depends(get_current_user)) -> User:
    return current_user
