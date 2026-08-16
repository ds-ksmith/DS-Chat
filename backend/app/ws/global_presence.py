import uuid

from redis.asyncio import Redis


class GlobalPresence:
    """Cross-instance "does this user have the app open at all right now,"
    independent of which (if any) room they currently have open -- backing
    the online/offline presence dot shown wherever a user's avatar renders.
    A single Redis hash (field = user_id, value = connection refcount),
    parallel to but separate from Presence's per-room hashes.

    Refcounted for the same reason as Presence: multiple tabs/instances for
    one user shouldn't flip them offline until the last connection closes.
    """

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    def _key(self) -> str:
        return "presence:global"

    async def connect(self, user_id: uuid.UUID) -> bool:
        """Returns True iff this was the user's first open connection --
        a genuine offline->online transition worth telling anyone about."""
        count = await self._redis.hincrby(self._key(), str(user_id), 1)
        return count == 1

    async def disconnect(self, user_id: uuid.UUID) -> bool:
        """Returns True iff this was the user's last open connection -- a
        genuine online->offline transition."""
        key = self._key()
        field = str(user_id)
        remaining = await self._redis.hincrby(key, field, -1)
        if remaining <= 0:
            await self._redis.hdel(key, field)
            return True
        return False

    async def is_online(self, user_id: uuid.UUID) -> bool:
        return await self._redis.hexists(self._key(), str(user_id))

    async def online_user_ids(self, user_ids: list[uuid.UUID]) -> set[uuid.UUID]:
        if not user_ids:
            return set()
        values = await self._redis.hmget(self._key(), [str(u) for u in user_ids])
        return {uid for uid, v in zip(user_ids, values) if v is not None}

    async def all_online_user_ids(self) -> set[uuid.UUID]:
        fields = await self._redis.hkeys(self._key())
        return {uuid.UUID(f) for f in fields}
