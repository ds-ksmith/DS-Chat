from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.webhook import IncomingWebhookPost
from app.services.message_events import broadcast_new_message
from app.services.webhook_service import WebhookNotFoundError, post_via_webhook

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


@router.post("/incoming/{token}", status_code=204)
async def incoming_webhook_endpoint(
    token: str,
    data: IncomingWebhookPost,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> None:
    # No auth dependency at all -- the token in the URL is the credential,
    # per ARCHITECTURE.md's incoming-webhook design.
    try:
        message, room, sender = await post_via_webhook(db, token, data.content)
    except WebhookNotFoundError:
        raise HTTPException(status_code=404, detail="Unknown webhook")

    broadcaster = request.app.state.broadcaster
    presence = request.app.state.presence
    await broadcast_new_message(db, broadcaster, presence, room.id, message, sender)
