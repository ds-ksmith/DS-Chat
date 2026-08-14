import json
import uuid

from redis.asyncio import Redis

from app.ws.connection_manager import ConnectionManager

ROOM_CHANNEL_PREFIX = "room:"


class RoomBroadcaster:
    """Cross-instance message fan-out (ARCHITECTURE.md phase 5).

    Publishes to a per-room Redis channel; every app instance -- including
    the one that published -- subscribes via a single pattern subscription
    and forwards to its own locally connected WebSocket clients via
    ConnectionManager. A single instance just talks to itself through Redis,
    so there's no separate code path for the 1-instance vs N-instance case.
    """

    def __init__(self, redis: Redis, manager: ConnectionManager) -> None:
        self._redis = redis
        self._manager = manager

    async def publish(self, room_id: uuid.UUID, payload: dict) -> None:
        await self._redis.publish(f"{ROOM_CHANNEL_PREFIX}{room_id}", json.dumps(payload))

    async def listen(self) -> None:
        pubsub = self._redis.pubsub()
        await pubsub.psubscribe(f"{ROOM_CHANNEL_PREFIX}*")
        try:
            async for message in pubsub.listen():
                if message["type"] != "pmessage":
                    continue
                channel = message["channel"]
                room_id = uuid.UUID(channel.removeprefix(ROOM_CHANNEL_PREFIX))
                payload = json.loads(message["data"])
                await self._manager.broadcast(room_id, payload)
        finally:
            await pubsub.punsubscribe(f"{ROOM_CHANNEL_PREFIX}*")
            await pubsub.aclose()
