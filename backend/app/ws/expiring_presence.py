import time
import uuid
from collections.abc import Callable

from redis.asyncio import Redis

# #77: an entry that isn't renewed for this long stops counting. Chosen as 3x
# the app-level ping interval (chat.py's WS_PING_INTERVAL_SECONDS): a healthy
# connection renews roughly every ping, so two missed beats are tolerated
# before someone flips offline.
PRESENCE_TTL_SECONDS = 90


def _text(value: str | bytes) -> str:
    return value.decode() if isinstance(value, bytes) else value


def _user_part(member: str) -> str:
    return member.split(":", 1)[0]


class ExpiringPresenceSet:
    """"Which users have at least one live connection" for one Redis key,
    where every connection is its own entry with its own expiry.

    This replaced per-user refcounts (#77): a refcount only goes down when a
    connection's cleanup code actually runs, so any connection that ended
    without it -- a server crash or reboot, a process killed mid-restart, a
    client that vanished without the server ever noticing -- left a +1 that
    nothing could ever subtract, showing that person online forever (and in
    the per-room case, suppressing their push notifications). Here a dead
    connection simply stops being renewed and ages out on its own, so there
    is no state that can leak.

    One sorted set per key: member `<user_id>:<connection_id>`, score = the
    moment it expires. "Live" means score > now. Scans are O(connections) --
    fine for a self-hosted team chat; only the global key grows with the
    whole server rather than one room.
    """

    def __init__(
        self,
        redis: Redis,
        ttl_seconds: float = PRESENCE_TTL_SECONDS,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._redis = redis
        self._ttl = ttl_seconds
        self._clock = clock

    @staticmethod
    def _member(user_id: uuid.UUID, conn_id: str) -> str:
        return f"{user_id}:{conn_id}"

    async def _live_members(self, key: str) -> list[str]:
        members = await self._redis.zrangebyscore(key, f"({self._clock()}", "+inf")
        return [_text(m) for m in members]

    async def add(self, key: str, user_id: uuid.UUID, conn_id: str) -> bool:
        """Creates or renews this connection's entry. Returns True iff the
        user had no live entry beforehand -- a genuine offline->online
        transition worth telling anyone about. Renewing an entry that's still
        live (the common case, every heartbeat) is a single cheap write."""
        member = self._member(user_id, conn_id)
        now = self._clock()
        score = await self._redis.zscore(key, member)
        came_online = False
        if score is None or score <= now:
            came_online = not await self.is_live(key, user_id)
        await self._redis.zadd(key, {member: now + self._ttl})
        # Lets a key nobody renews any more (an idle room) disappear on its
        # own instead of sitting there holding only expired entries.
        await self._redis.expire(key, int(self._ttl * 2))
        return came_online

    async def remove(self, key: str, user_id: uuid.UUID, conn_id: str) -> bool:
        """Drops this connection's entry. Returns True iff that left the user
        with no live entry -- a genuine online->offline transition. False if
        the entry was already gone: whoever removed it (see prune) already
        reported the transition, and reporting it twice would be noise."""
        removed = await self._redis.zrem(key, self._member(user_id, conn_id))
        if not removed:
            return False
        return not await self.is_live(key, user_id)

    async def is_live(self, key: str, user_id: uuid.UUID) -> bool:
        prefix = f"{user_id}:"
        return any(m.startswith(prefix) for m in await self._live_members(key))

    async def live_user_ids(self, key: str) -> set[uuid.UUID]:
        return {uuid.UUID(_user_part(m)) for m in await self._live_members(key)}

    async def prune(self, key: str) -> set[uuid.UUID]:
        """Deletes expired entries. Returns the users whose last live entry
        was among them -- the offline transitions nobody was told about,
        since an expiry has no disconnect event to hang a broadcast on."""
        now = self._clock()
        expired = [_text(m) for m in await self._redis.zrangebyscore(key, "-inf", now)]
        if not expired:
            return set()
        await self._redis.zremrangebyscore(key, "-inf", now)
        gone = {_user_part(m) for m in expired} - {_user_part(m) for m in await self._live_members(key)}
        return {uuid.UUID(u) for u in gone}
