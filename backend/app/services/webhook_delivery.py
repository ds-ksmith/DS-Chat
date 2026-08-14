import hashlib
import hmac
import json
import logging

import httpx

from app.models import EventSubscription

logger = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 5.0


async def deliver_event(subscription: EventSubscription, event_type: str, payload: dict) -> None:
    """POST a signed event to a subscription's target_url.

    Fire-once, best-effort: no retry/backoff, any failure is logged and
    swallowed rather than raised -- a slow or dead third-party endpoint must
    never affect message delivery to real room members. Safe to run in a
    background asyncio.create_task (unlike the Phase 4 push lesson) because
    there's no DB session involved here, just the already-serialized
    payload and secret -- nothing that can outlive an event loop.
    """
    body = json.dumps({"event": event_type, "data": payload}).encode()
    signature = hmac.new(subscription.signing_secret.encode(), body, hashlib.sha256).hexdigest()

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            await client.post(
                subscription.target_url,
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-KeepItTalking-Signature": f"sha256={signature}",
                },
            )
    except httpx.HTTPError:
        logger.warning(
            "Failed to deliver %s event to subscription %s", event_type, subscription.id
        )
