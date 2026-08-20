import uuid

from redis.asyncio import Redis


class FocusPresence:
    """Cross-instance "is this desktop-mode user's window currently
    unfocused," used only to widen desktop_notification/push eligibility
    beyond plain room-connection state (#59). A Redis hash (field =
    user_id, value = refcount of that user's currently-blurred desktop
    connections), parallel to Presence/GlobalPresence.

    Absence from this hash is the default and means "focused." That default
    is also exactly right for every browser-tab connection: only the
    desktop client ever sends focus/blur frames at all (see chat.py's
    "focus" envelope handling), so a browser user never appears here --
    their attention is already fully captured by Presence's room-connection
    state, which stays visibility-gated with no separate focus signal.

    Refcounted for the same multi-connection reason as Presence/
    GlobalPresence, with the same known simplification: two desktop windows
    for one user, one focused and one blurred, count as "unfocused" here
    (refcount > 0) even though the user does have attention somewhere. That
    errs toward notifying rather than silently missing one, which is the
    safer failure mode for a notification.
    """

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    def _key(self) -> str:
        return "presence:unfocused"

    async def mark_blurred(self, user_id: uuid.UUID) -> None:
        await self._redis.hincrby(self._key(), str(user_id), 1)

    async def mark_focused(self, user_id: uuid.UUID) -> None:
        key = self._key()
        field = str(user_id)
        remaining = await self._redis.hincrby(key, field, -1)
        if remaining <= 0:
            await self._redis.hdel(key, field)

    async def is_unfocused(self, user_id: uuid.UUID) -> bool:
        return await self._redis.hexists(self._key(), str(user_id))
