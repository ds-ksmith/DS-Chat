import asyncio
import json
import logging
import uuid
from urllib.parse import urlparse

from pywebpush import WebPushException, webpush
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import PushSubscription
from app.schemas.push import PushSubscriptionCreate

logger = logging.getLogger(__name__)


async def subscribe(
    db: AsyncSession, user_id: uuid.UUID, data: PushSubscriptionCreate
) -> PushSubscription:
    # Upsert by endpoint: the same device/browser re-subscribing (e.g. after
    # a key rotation, or logging in as someone else on a shared device)
    # updates the existing row rather than erroring on the unique constraint.
    stmt = (
        pg_insert(PushSubscription)
        .values(
            user_id=user_id,
            endpoint=data.endpoint,
            p256dh_key=data.keys.p256dh,
            auth_key=data.keys.auth,
        )
        .on_conflict_do_update(
            index_elements=[PushSubscription.endpoint],
            set_={
                "user_id": user_id,
                "p256dh_key": data.keys.p256dh,
                "auth_key": data.keys.auth,
            },
        )
        .returning(PushSubscription)
    )
    result = await db.execute(stmt)
    await db.commit()
    return result.scalar_one()


async def unsubscribe(db: AsyncSession, user_id: uuid.UUID, endpoint: str) -> None:
    await db.execute(
        delete(PushSubscription).where(
            PushSubscription.user_id == user_id, PushSubscription.endpoint == endpoint
        )
    )
    await db.commit()


# #56 correction: bumping to pywebpush's latest release (2.4.0) turned out
# not to actually fix WNS -- checked the installed package's own source
# directly and it has no WNS-specific code anywhere; the upstream
# discussion (web-push-libs/pywebpush#162) apparently never shipped.
# Worked around here instead, using the `headers` param webpush() already
# exposes for exactly this: WNS (Windows/Edge push,
# *.notify.windows.com) has required this header since April 2024, or it
# 400s with no useful body -- "cache" for a non-zero TTL, "no-cache" for
# zero (this app never sets a TTL, so always the latter).
def _is_wns_endpoint(endpoint: str) -> bool:
    return urlparse(endpoint).hostname is not None and urlparse(endpoint).hostname.endswith(
        "notify.windows.com"
    )


def _send_one(subscription: PushSubscription, payload: dict) -> None:
    extra_headers = {"X-WNS-Cache-Policy": "no-cache"} if _is_wns_endpoint(subscription.endpoint) else None
    webpush(
        subscription_info={
            "endpoint": subscription.endpoint,
            "keys": {"p256dh": subscription.p256dh_key, "auth": subscription.auth_key},
        },
        data=json.dumps(payload),
        vapid_private_key=settings.vapid_private_key,
        vapid_claims={"sub": settings.vapid_subject},
        headers=extra_headers,
    )


async def send_push_to_user(db: AsyncSession, user_id: uuid.UUID, payload: dict) -> None:
    """Called (awaited) from the WS handler after broadcasting to connected
    clients, so it never delays delivery to anyone actually online. Runs
    sequentially against the caller's session rather than firing background
    asyncio.create_task()s -- those can easily outlive the request/test event
    loop they were created on, and AsyncSession isn't safe to touch from two
    coroutines concurrently, so a fire-and-forget task per subscription would
    risk exactly that. Each webpush() call itself still runs off the event
    loop via asyncio.to_thread (pywebpush is synchronous)."""
    if not settings.vapid_private_key:
        logger.debug("VAPID keys not configured; skipping push to %s", user_id)
        return

    result = await db.execute(
        select(PushSubscription).where(PushSubscription.user_id == user_id)
    )
    subscriptions = list(result.scalars().all())

    for subscription in subscriptions:
        try:
            await asyncio.to_thread(_send_one, subscription, payload)
        except WebPushException as exc:
            status = exc.response.status_code if exc.response is not None else None
            if status in (404, 410):
                # Subscription is gone (browser unsubscribed, expired, etc.)
                await db.execute(
                    delete(PushSubscription).where(PushSubscription.id == subscription.id)
                )
                await db.commit()
            else:
                # #56: WNS's own 400s carry the actual reason in a response
                # *header* ("Ttl value conflicts with X-WNS-Cache-Policy"),
                # not the body -- pywebpush's own exception message only
                # ever surfaces the body, so that specific bug still would
                # have needed a full journalctl+DB-dump investigation to
                # diagnose even with a body-only log line. Logging headers
                # too is the difference between "something is broken" and
                # this log line alone being enough next time, for any push
                # provider's failure, not just WNS's.
                response = exc.response
                detail = ""
                if response is not None:
                    detail = f" | response: {response.text!r} | headers: {dict(response.headers)!r}"
                logger.warning("Push delivery failed for %s: %s%s", subscription.id, exc, detail)
