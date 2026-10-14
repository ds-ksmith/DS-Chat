import uuid

from redis.asyncio import Redis

from app.ws.expiring_presence import ExpiringPresenceSet


class FocusPresence:
    """Cross-instance "is this desktop-mode user's window currently
    unfocused," used only to widen desktop_notification/push eligibility
    beyond plain room-connection state (#59). One expiring entry per
    currently-blurred desktop connection (see ExpiringPresenceSet),
    parallel to Presence/GlobalPresence.

    Absence from the set is the default and means "focused." That default
    is also exactly right for every browser-tab connection: only the
    desktop client ever sends focus/blur frames at all (see chat.py's
    "focus" envelope handling), so a browser user never appears here --
    their attention is already fully captured by Presence's room-connection
    state, which stays visibility-gated with no separate focus signal.

    Same known simplification as before: two desktop windows for one user,
    one focused and one blurred, count as "unfocused" (any live blurred
    entry) even though the user does have attention somewhere. That errs
    toward notifying rather than silently missing one, which is the safer
    failure mode for a notification. Entries expire (#77) -- a desktop
    window that died while blurred used to leave its user "unfocused"
    forever.
    """

    KEY = "presence:v2:unfocused"

    def __init__(self, redis: Redis, store: ExpiringPresenceSet | None = None) -> None:
        self._store = store or ExpiringPresenceSet(redis)

    async def mark_blurred(self, user_id: uuid.UUID, conn_id: str) -> None:
        await self._store.add(self.KEY, user_id, conn_id)

    async def mark_focused(self, user_id: uuid.UUID, conn_id: str) -> None:
        await self._store.remove(self.KEY, user_id, conn_id)

    async def refresh(self, user_id: uuid.UUID, conn_id: str) -> None:
        await self._store.add(self.KEY, user_id, conn_id)

    async def is_unfocused(self, user_id: uuid.UUID) -> bool:
        return await self._store.is_live(self.KEY, user_id)
