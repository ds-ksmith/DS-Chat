from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models import User
from app.schemas.push import (
    PushSubscriptionCreate,
    PushUnsubscribeRequest,
    VapidPublicKeyRead,
)
from app.services.push_service import subscribe, unsubscribe

router = APIRouter(prefix="/api/push", tags=["push"])


@router.get("/vapid-public-key", response_model=VapidPublicKeyRead)
async def get_vapid_public_key(current_user: User = Depends(get_current_user)):
    return VapidPublicKeyRead(public_key=settings.vapid_public_key)


@router.post("/subscribe", status_code=204)
async def subscribe_endpoint(
    data: PushSubscriptionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    await subscribe(db, current_user.id, data)
    return Response(status_code=204)


@router.delete("/subscribe", status_code=204)
async def unsubscribe_endpoint(
    data: PushUnsubscribeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    await unsubscribe(db, current_user.id, data.endpoint)
    return Response(status_code=204)
