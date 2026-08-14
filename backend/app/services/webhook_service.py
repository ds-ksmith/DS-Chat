import asyncio
import uuid

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import EventSubscription, Message, Room, User, WebhookIncoming
from app.security import generate_token
from app.services.message_service import create_message
from app.services.ssrf import validate_target_url
from app.services.webhook_delivery import deliver_event

VALID_EVENT_TYPES = {"message.created", "message.updated"}


class WebhookNotFoundError(Exception):
    pass


class InvalidEventTypeError(Exception):
    pass


class SubscriptionNotFoundError(Exception):
    pass


async def create_incoming_webhook(
    db: AsyncSession, actor: User, room_id: uuid.UUID, description: str | None
) -> WebhookIncoming:
    webhook = WebhookIncoming(
        room_id=room_id, token=generate_token(), created_by=actor.id, description=description
    )
    db.add(webhook)
    try:
        await db.commit()
    except IntegrityError:
        # A token collision is astronomically unlikely (256 bits of
        # randomness) -- surface it rather than silently masking it.
        await db.rollback()
        raise
    await db.refresh(webhook)
    return webhook


async def list_incoming_webhooks(db: AsyncSession, room_id: uuid.UUID) -> list[WebhookIncoming]:
    result = await db.execute(
        select(WebhookIncoming)
        .where(WebhookIncoming.room_id == room_id)
        .order_by(WebhookIncoming.created_at)
    )
    return list(result.scalars().all())


async def revoke_incoming_webhook(
    db: AsyncSession, room_id: uuid.UUID, webhook_id: uuid.UUID
) -> None:
    webhook = await db.get(WebhookIncoming, webhook_id)
    if webhook is None or webhook.room_id != room_id:
        raise WebhookNotFoundError()
    await db.delete(webhook)
    await db.commit()


async def list_all_incoming_webhooks_admin(db: AsyncSession) -> list[WebhookIncoming]:
    result = await db.execute(
        select(WebhookIncoming)
        .options(selectinload(WebhookIncoming.room), selectinload(WebhookIncoming.creator))
        .order_by(WebhookIncoming.created_at.desc())
    )
    return list(result.scalars().all())


async def post_via_webhook(db: AsyncSession, token: str, content: str) -> tuple[Message, Room, User]:
    result = await db.execute(
        select(WebhookIncoming)
        .where(WebhookIncoming.token == token)
        .options(selectinload(WebhookIncoming.room), selectinload(WebhookIncoming.creator))
    )
    webhook = result.scalar_one_or_none()
    if webhook is None:
        raise WebhookNotFoundError()

    message = await create_message(db, webhook.room_id, webhook.created_by, content)
    return message, webhook.room, webhook.creator


async def create_event_subscription(
    db: AsyncSession,
    actor: User,
    room_id: uuid.UUID | None,
    event_types: list[str],
    target_url: str,
) -> tuple[EventSubscription, str]:
    if not set(event_types) <= VALID_EVENT_TYPES:
        raise InvalidEventTypeError()
    validate_target_url(target_url)

    secret = generate_token()
    subscription = EventSubscription(
        room_id=room_id,
        event_types=event_types,
        target_url=target_url,
        signing_secret=secret,
        created_by=actor.id,
    )
    db.add(subscription)
    await db.commit()
    await db.refresh(subscription)
    return subscription, secret


async def list_event_subscriptions(db: AsyncSession, room_id: uuid.UUID) -> list[EventSubscription]:
    result = await db.execute(
        select(EventSubscription)
        .where(EventSubscription.room_id == room_id)
        .order_by(EventSubscription.created_at)
    )
    return list(result.scalars().all())


async def revoke_event_subscription(
    db: AsyncSession, room_id: uuid.UUID, subscription_id: uuid.UUID
) -> None:
    subscription = await db.get(EventSubscription, subscription_id)
    if subscription is None or subscription.room_id != room_id:
        raise SubscriptionNotFoundError()
    await db.delete(subscription)
    await db.commit()


async def list_all_event_subscriptions_admin(db: AsyncSession) -> list[EventSubscription]:
    result = await db.execute(
        select(EventSubscription)
        .options(selectinload(EventSubscription.room), selectinload(EventSubscription.creator))
        .order_by(EventSubscription.created_at.desc())
    )
    return list(result.scalars().all())


async def dispatch_event(
    db: AsyncSession, event_type: str, room_id: uuid.UUID, payload: dict
) -> None:
    result = await db.execute(
        select(EventSubscription).where(
            or_(EventSubscription.room_id == room_id, EventSubscription.room_id.is_(None))
        )
    )
    for subscription in result.scalars().all():
        if event_type in subscription.event_types:
            asyncio.create_task(deliver_event(subscription, event_type, payload))
