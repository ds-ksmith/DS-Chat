import asyncio
import logging
import uuid
from collections.abc import Callable

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.message_events import broadcast_dm_presence_update, broadcast_member_updated
from app.ws.broadcaster import Broadcaster
from app.ws.global_presence import GlobalPresence

logger = logging.getLogger(__name__)

PRESENCE_SWEEP_INTERVAL_SECONDS = 15
SWEEP_LOCK_KEY = "presence:v2:sweeper-lock"


async def sweep_once(
    redis: Redis,
    global_presence: GlobalPresence,
    broadcaster: Broadcaster,
    session_factory: Callable[[], AsyncSession],
    lock_seconds: int | None = max(1, PRESENCE_SWEEP_INTERVAL_SECONDS - 1),
) -> set[uuid.UUID]:
    """Expires dead connections' presence entries and tells everyone about
    the users that went offline as a result.

    A clean disconnect broadcasts its own offline transition (chat.py), but a
    connection that just stops being renewed has no such event -- this is the
    only thing that notices. Every app worker runs this loop; the Redis lock
    makes it one sweep per interval across the whole deployment rather than
    N workers each doing (and broadcasting) the same thing. `lock_seconds=None`
    skips the lock (tests).
    """
    if lock_seconds is not None and not await redis.set(SWEEP_LOCK_KEY, "1", nx=True, ex=lock_seconds):
        return set()
    went_offline = await global_presence.sweep()
    for user_id in went_offline:
        # One user's failed broadcast must not cost everyone after them
        # theirs -- their entry is already gone, so this is the only chance.
        try:
            async with session_factory() as db:
                await broadcast_member_updated(db, broadcaster, user_id)
                await broadcast_dm_presence_update(db, broadcaster, user_id, online=False)
        except Exception:
            logger.error("Failed to broadcast offline for %s", user_id, exc_info=True)
    return went_offline


async def run_presence_sweeper(app, interval: float = PRESENCE_SWEEP_INTERVAL_SECONDS) -> None:
    # Same lesson as Broadcaster.run_forever (#76): a background task that
    # dies on its first error does so silently, and here that would quietly
    # bring the stuck-online bug back.
    while True:
        await asyncio.sleep(interval)
        try:
            await sweep_once(
                app.state.redis,
                app.state.global_presence,
                app.state.broadcaster,
                app.state.session_factory,
                lock_seconds=max(1, int(interval) - 1),
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.error("Presence sweep failed", exc_info=True)


async def purge_legacy_presence(redis: Redis) -> int:
    """Deletes the old refcount hashes (`presence:global`, `presence:unfocused`,
    `presence:{room_id}`). Nothing reads them any more -- the live data is
    under `presence:v2:` -- and they hold whatever counts leaked before #77,
    so there's nothing worth keeping. Safe to run on every startup."""
    deleted = 0
    async for key in redis.scan_iter("presence:*"):
        name = key.decode() if isinstance(key, bytes) else key
        if name.startswith("presence:v2:"):
            continue
        await redis.delete(name)
        deleted += 1
    return deleted
