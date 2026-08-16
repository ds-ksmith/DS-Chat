import json
import uuid

from redis.asyncio import Redis

from app.ws.connection_manager import ConnectionManager

ROOM_CHANNEL_PREFIX = "room:"
USER_CHANNEL_PREFIX = "user:"


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

    async def listen(self) -> None:
        pubsub = self._redis.pubsub()
        await pubsub.psubscribe(f"{ROOM_CHANNEL_PREFIX}*", f"{USER_CHANNEL_PREFIX}*")
        try:
            async for message in pubsub.listen():
                if message["type"] != "pmessage":
                    continue
                channel = message["channel"]
                payload = json.loads(message["data"])
                if channel.startswith(ROOM_CHANNEL_PREFIX):
                    room_id = uuid.UUID(channel.removeprefix(ROOM_CHANNEL_PREFIX))
                    await self._manager.broadcast(room_id, payload)
                elif channel.startswith(USER_CHANNEL_PREFIX):
                    user_id = uuid.UUID(channel.removeprefix(USER_CHANNEL_PREFIX))
                    await self._manager.send_to_user(user_id, payload)
        finally:
            await pubsub.punsubscribe(f"{ROOM_CHANNEL_PREFIX}*", f"{USER_CHANNEL_PREFIX}*")
            await pubsub.aclose()
