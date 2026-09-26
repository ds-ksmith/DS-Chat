import asyncio
import contextlib
import json
import logging
import uuid

from redis.asyncio import Redis

from app.ws.connection_manager import ConnectionManager

logger = logging.getLogger(__name__)

ROOM_CHANNEL_PREFIX = "room:"
USER_CHANNEL_PREFIX = "user:"

# #76: a run shorter than this before dying doesn't count as "stable" for
# resetting the backoff in run_forever() below -- long enough that a real,
# working connection has clearly settled in, short enough not to leave a
# just-recovered listener exposed to a full backoff climb if Redis blips
# again shortly after reconnecting.
STABLE_RUN_SECONDS = 60
MAX_BACKOFF_SECONDS = 30


class Broadcaster:
    """Cross-instance message fan-out (ARCHITECTURE.md phase 5).

    Publishes to a per-room or per-user Redis channel; every app instance --
    including the one that published -- subscribes via a single pattern
    subscription and forwards to its own locally connected WebSocket clients
    via ConnectionManager. A single instance just talks to itself through
    Redis, so there's no separate code path for the 1-instance vs N-instance
    case.

    Room channels carry anything scoped to a room's joined members (new
    messages, edits, reactions). User channels carry anything scoped to one
    person regardless of which rooms they've joined -- currently just
    "you've been added to a room," which by definition arrives before the
    recipient could ever have joined that room's own channel.
    """

    def __init__(self, redis: Redis, manager: ConnectionManager) -> None:
        self._redis = redis
        self._manager = manager

    async def publish(self, room_id: uuid.UUID, payload: dict) -> None:
        await self._redis.publish(f"{ROOM_CHANNEL_PREFIX}{room_id}", json.dumps(payload))

    async def publish_to_user(self, user_id: uuid.UUID, payload: dict) -> None:
        await self._redis.publish(f"{USER_CHANNEL_PREFIX}{user_id}", json.dumps(payload))

    async def run_forever(self) -> None:
        """Supervises listen(), restarting it if it ever dies.

        #76's real root cause, found after the per-message try/except below
        turned out not to be enough: this is the *one* pubsub listener for
        the whole process (see main.py's lifespan), created once at startup
        with nothing watching over it afterward. A connection-level failure
        -- Redis restarting, a network blip between the app and Redis --
        raises from the `async for` iteration in listen() itself, outside
        that per-message guard, and previously killed this task permanently
        and silently: HTTP/REST and login kept working fine (neither
        touches this), but live message delivery was gone for every room
        and every user on this instance until the whole process was
        restarted. Confirmed live in production: Redis got restarted by an
        OS update, and `PUBSUB NUMPAT` against it afterward showed zero
        pattern subscriptions across all 4 gunicorn workers -- every one of
        them had silently lost its listener with nothing to bring it back.
        """
        backoff_seconds = 1.0
        while True:
            started_at = asyncio.get_event_loop().time()
            try:
                await self.listen()
                logger.warning("Broadcaster.listen() exited without error -- restarting")
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.error("Broadcaster.listen() failed -- restarting", exc_info=True)
            ran_for = asyncio.get_event_loop().time() - started_at
            # Sleep at the *current* backoff first, then grow it for next
            # time -- computing the next value before sleeping would skip
            # straight past the first (shortest) retry delay.
            await asyncio.sleep(backoff_seconds)
            backoff_seconds = (
                1.0 if ran_for > STABLE_RUN_SECONDS else min(backoff_seconds * 2, MAX_BACKOFF_SECONDS)
            )

    async def listen(self) -> None:
        pubsub = self._redis.pubsub()
        await pubsub.psubscribe(f"{ROOM_CHANNEL_PREFIX}*", f"{USER_CHANNEL_PREFIX}*")
        try:
            async for message in pubsub.listen():
                if message["type"] != "pmessage":
                    continue
                # #76: this is the one pubsub listener for the whole process
                # (see main.py's lifespan) -- ConnectionManager.broadcast/
                # send_to_user already guard against one dead socket taking
                # the rest of a single fan-out down, but this belt-and-
                # suspenders catch is for anything else unexpected (a
                # malformed payload, e.g.) doing the same. An uncaught
                # exception here previously meant *this whole async for*
                # loop died silently -- no more live delivery to any room on
                # this instance, for anyone, until the process restarted.
                try:
                    channel = message["channel"]
                    payload = json.loads(message["data"])
                    if channel.startswith(ROOM_CHANNEL_PREFIX):
                        room_id = uuid.UUID(channel.removeprefix(ROOM_CHANNEL_PREFIX))
                        await self._manager.broadcast(room_id, payload)
                    elif channel.startswith(USER_CHANNEL_PREFIX):
                        user_id = uuid.UUID(channel.removeprefix(USER_CHANNEL_PREFIX))
                        await self._manager.send_to_user(user_id, payload)
                except Exception:
                    logger.error("Error handling pubsub message on channel %s", message.get("channel"), exc_info=True)
        finally:
            # #76: reached via a connection that's already dead just as
            # often as a clean shutdown (that's the whole failure mode
            # run_forever() now recovers from) -- punsubscribe/aclose over
            # a broken connection would themselves raise, masking whatever
            # actually killed the loop above and, since run_forever() only
            # starts backing off *after* listen() returns/raises, delaying
            # the reconnect for no benefit (a fresh pubsub object is about
            # to be created on retry regardless of whether this cleanup
            # succeeded).
            with contextlib.suppress(Exception):
                await pubsub.punsubscribe(f"{ROOM_CHANNEL_PREFIX}*", f"{USER_CHANNEL_PREFIX}*")
            with contextlib.suppress(Exception):
                await pubsub.aclose()
