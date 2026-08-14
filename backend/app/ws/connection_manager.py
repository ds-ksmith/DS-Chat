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

    def join(self, room_id: uuid.UUID, websocket: WebSocket) -> None:
        self._rooms[room_id].add(websocket)

    def leave(self, room_id: uuid.UUID, websocket: WebSocket) -> None:
        self._rooms[room_id].discard(websocket)
        if not self._rooms[room_id]:
            del self._rooms[room_id]

    def leave_all(self, websocket: WebSocket) -> None:
        for room_id in list(self._rooms.keys()):
            self.leave(room_id, websocket)

    async def broadcast(self, room_id: uuid.UUID, payload: dict) -> None:
        for websocket in list(self._rooms.get(room_id, ())):
            await websocket.send_json(payload)
