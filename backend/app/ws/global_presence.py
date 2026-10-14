import uuid

from redis.asyncio import Redis

from app.ws.expiring_presence import ExpiringPresenceSet


class GlobalPresence:
    """Cross-instance "does this user have the app open at all right now,"
    independent of which (if any) room they currently have open -- backing
    the online/offline presence dot shown wherever a user's avatar renders.

    Each connection has its own expiring entry (see ExpiringPresenceSet), so
    a user with several tabs/devices stays online until the last one goes,
    and a connection that dies without cleaning up ages out instead of
    leaving them online forever (#77). The key is versioned (`v2`) because
    the old refcount hash lives at `presence:global` and its leaked counts
    must not be read as live entries.
    """

    KEY = "presence:v2:global"

    def __init__(self, redis: Redis, store: ExpiringPresenceSet | None = None) -> None:
        self._store = store or ExpiringPresenceSet(redis)

    async def connect(self, user_id: uuid.UUID, conn_id: str) -> bool:
        """Returns True iff this made the user newly online -- a genuine
        offline->online transition worth telling anyone about."""
        return await self._store.add(self.KEY, user_id, conn_id)

    async def refresh(self, user_id: uuid.UUID, conn_id: str) -> bool:
        """Heartbeat. Same as connect() on purpose: a connection whose entry
        had already expired (a long stall) comes back online here, and the
        caller needs to announce that exactly like a fresh connect."""
        return await self._store.add(self.KEY, user_id, conn_id)

    async def disconnect(self, user_id: uuid.UUID, conn_id: str) -> bool:
        """Returns True iff that was the user's last live connection -- a
        genuine online->offline transition."""
        return await self._store.remove(self.KEY, user_id, conn_id)

    async def sweep(self) -> set[uuid.UUID]:
        """Drops expired entries and returns the users that went offline as a
        result -- the transitions no disconnect ever reported."""
        return await self._store.prune(self.KEY)

    async def is_online(self, user_id: uuid.UUID) -> bool:
        return await self._store.is_live(self.KEY, user_id)

    async def online_user_ids(self, user_ids: list[uuid.UUID]) -> set[uuid.UUID]:
        if not user_ids:
            return set()
        return set(user_ids) & await self._store.live_user_ids(self.KEY)

    async def all_online_user_ids(self) -> set[uuid.UUID]:
        return await self._store.live_user_ids(self.KEY)
