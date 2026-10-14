import uuid

from redis.asyncio import Redis

from app.ws.expiring_presence import ExpiringPresenceSet


class Presence:
    """Cross-instance "who's connected to this room," one expiring set per
    room (see ExpiringPresenceSet).

    This is what the offline-push check reads, so a leaked entry used to mean
    a user who'd gone away was still treated as "watching the room" and never
    got a push notification (#77). Entries now expire unless the connection
    keeps renewing them, so that can't outlive a dead connection by more than
    the TTL. Keys are versioned (`v2`) so the old refcount hashes
    (`presence:{room_id}`), with whatever they leaked, are never read.
    """

    def __init__(self, redis: Redis, store: ExpiringPresenceSet | None = None) -> None:
        self._store = store or ExpiringPresenceSet(redis)

    def _key(self, room_id: uuid.UUID) -> str:
        return f"presence:v2:room:{room_id}"

    async def join(self, room_id: uuid.UUID, user_id: uuid.UUID, conn_id: str) -> None:
        key = self._key(room_id)
        # Per-room offline transitions aren't broadcast anywhere, so unlike
        # the global key there's nothing to lose by pruning here -- it just
        # keeps a busy room's set from accumulating expired entries.
        await self._store.prune(key)
        await self._store.add(key, user_id, conn_id)

    async def refresh(self, room_id: uuid.UUID, user_id: uuid.UUID, conn_id: str) -> None:
        await self._store.add(self._key(room_id), user_id, conn_id)

    async def leave(self, room_id: uuid.UUID, user_id: uuid.UUID, conn_id: str) -> None:
        await self._store.remove(self._key(room_id), user_id, conn_id)

    async def connected_user_ids(self, room_id: uuid.UUID) -> set[uuid.UUID]:
        return await self._store.live_user_ids(self._key(room_id))
