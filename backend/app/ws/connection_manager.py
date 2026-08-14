import uuid
from collections import defaultdict

from fastapi import WebSocket


class ConnectionManager:
    """In-memory, single-process WebSocket registry.

    Correct for a single app-server instance only; cross-instance fan-out via
    Redis pub/sub is a later phase (ARCHITECTURE.md phase 5).
    """

    def __init__(self) -> None:
        self._rooms: dict[uuid.UUID, set[WebSocket]] = defaultdict(set)
        # A single connection can be joined to multiple rooms at once (one
        # `join` message per room over the same socket), so this is keyed on
        # the socket alone, not per-room.
        self._ws_user: dict[WebSocket, uuid.UUID] = {}

    def join(self, room_id: uuid.UUID, websocket: WebSocket, user_id: uuid.UUID) -> None:
        self._rooms[room_id].add(websocket)
        self._ws_user[websocket] = user_id

    def leave(self, room_id: uuid.UUID, websocket: WebSocket) -> None:
        self._rooms[room_id].discard(websocket)
        if not self._rooms[room_id]:
            del self._rooms[room_id]

    def leave_all(self, websocket: WebSocket) -> None:
        for room_id in list(self._rooms.keys()):
            self.leave(room_id, websocket)
        self._ws_user.pop(websocket, None)

    def connected_user_ids(self, room_id: uuid.UUID) -> set[uuid.UUID]:
        """Users (not just sockets) with an active connection to this room --
        used to skip push notifications for anyone already watching, per
        ARCHITECTURE.md's "members with no active connection" push flow."""
        return {
            self._ws_user[ws] for ws in self._rooms.get(room_id, ()) if ws in self._ws_user
        }

    async def broadcast(self, room_id: uuid.UUID, payload: dict) -> None:
        for websocket in list(self._rooms.get(room_id, ())):
            await websocket.send_json(payload)
