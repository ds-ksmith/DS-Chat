import logging
import uuid
from collections import defaultdict

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Local, single-process WebSocket socket registry.

    Purely about delivering to sockets connected to *this* process --
    cross-instance fan-out lives in Broadcaster, and cross-instance "who's
    connected" for push lives in Presence, both backed by Redis
    (ARCHITECTURE.md phase 5).
    """

    def __init__(self) -> None:
        self._rooms: dict[uuid.UUID, set[WebSocket]] = defaultdict(set)
        self._users: dict[uuid.UUID, set[WebSocket]] = defaultdict(set)

    def join(self, room_id: uuid.UUID, websocket: WebSocket) -> None:
        self._rooms[room_id].add(websocket)

    def leave(self, room_id: uuid.UUID, websocket: WebSocket) -> None:
        self._rooms[room_id].discard(websocket)
        if not self._rooms[room_id]:
            del self._rooms[room_id]

    def leave_all(self, websocket: WebSocket) -> None:
        for room_id in list(self._rooms.keys()):
            self.leave(room_id, websocket)

    def register_user(self, user_id: uuid.UUID, websocket: WebSocket) -> None:
        """Ties a socket to the authenticated user who owns it, independent
        of which (if any) room it has joined -- lets a user be reached the
        instant they're added to a room, before they've ever joined that
        room's channel."""
        self._users[user_id].add(websocket)

    def unregister_user(self, user_id: uuid.UUID, websocket: WebSocket) -> None:
        self._users[user_id].discard(websocket)
        if not self._users[user_id]:
            del self._users[user_id]

    async def broadcast(self, room_id: uuid.UUID, payload: dict) -> None:
        for websocket in list(self._rooms.get(room_id, ())):
            # #76: one dead/racing socket (e.g. its own disconnect cleanup
            # hasn't finished removing it from _rooms yet) must not take the
            # rest of this broadcast down with it -- this runs inside
            # Broadcaster.listen()'s single, never-restarted per-process
            # pubsub loop, so an unhandled exception here previously meant
            # one bad socket silently killed *live delivery for every room
            # on this instance*, not just the one socket, until the process
            # was restarted.
            try:
                await websocket.send_json(payload)
            except Exception:
                logger.warning("Dropping dead socket during broadcast to room %s", room_id, exc_info=True)

    async def send_to_user(self, user_id: uuid.UUID, payload: dict) -> None:
        for websocket in list(self._users.get(user_id, ())):
            try:
                await websocket.send_json(payload)
            except Exception:
                logger.warning("Dropping dead socket sending to user %s", user_id, exc_info=True)
