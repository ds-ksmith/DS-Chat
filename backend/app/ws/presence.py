import uuid

from redis.asyncio import Redis


class Presence:
    """Cross-instance "who's connected to this room," backed by a Redis hash
    per room (field = user_id, value = connection refcount).

    Refcounted rather than a plain set so a user with two connections to the
    same room -- two tabs, or one per app instance -- doesn't get marked
    offline when only one of those connections closes.

    Known limitation: a hard crash (not a clean disconnect) leaks that
    connection's increment forever, since there's no heartbeat/TTL here to
    reclaim it -- out of scope for this phase, same category of
    simplification as the "no server-side session revocation" note in the
    README.
    """

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    def _key(self, room_id: uuid.UUID) -> str:
        return f"presence:{room_id}"

    async def join(self, room_id: uuid.UUID, user_id: uuid.UUID) -> None:
        await self._redis.hincrby(self._key(room_id), str(user_id), 1)

    async def leave(self, room_id: uuid.UUID, user_id: uuid.UUID) -> None:
        key = self._key(room_id)
        field = str(user_id)
        remaining = await self._redis.hincrby(key, field, -1)
        if remaining <= 0:
            await self._redis.hdel(key, field)

    async def connected_user_ids(self, room_id: uuid.UUID) -> set[uuid.UUID]:
        fields = await self._redis.hkeys(self._key(room_id))
        return {uuid.UUID(f) for f in fields}
