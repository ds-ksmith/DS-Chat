import uuid

from sqlalchemy import select

from app.models import MessageRoomReference
from app.schemas.user import UserCreate
from app.services.auth_service import register_user


def _unique(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _recv(ws) -> dict:
    """Reads the next frame, discarding member_updated presence-change
    broadcasts -- same convention as test_mentions.py."""
    while True:
        msg = ws.receive_json()
        if msg.get("type") != "member_updated":
            return msg


def _register_ws(ws_client, username: str) -> dict:
    async def _seed():
        async with ws_client.session_factory() as session:
            await register_user(
                session,
                UserCreate(username=username, email=f"{username}@example.com", password="password123"),
            )

    ws_client.portal.call(_seed)
    resp = ws_client.post(
        "/api/auth/login", json={"username_or_email": username, "password": "password123"}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _send_and_sync(ws, room_id: str, content: str) -> dict:
    """Sync barrier -- see test_mentions.py's identical helper. Proves the
    message frame's full handling (including room-reference extraction) has
    completed before the test checks anything."""
    ws.send_json({"type": "message", "room_id": room_id, "content": content})
    message = ws.receive_json()
    ws.send_json({"type": "join", "room_id": room_id})
    assert ws.receive_json()["type"] == "joined"
    return message


def _referenced_room_ids(ws_client, message_id: str) -> set[str]:
    async def _query():
        async with ws_client.session_factory() as session:
            result = await session.execute(
                select(MessageRoomReference.room_id).where(
                    MessageRoomReference.message_id == uuid.UUID(message_id)
                )
            )
            return {str(row[0]) for row in result.all()}

    return ws_client.portal.call(_query)


def test_room_reference_to_own_room_is_stored(ws_client):
    username = _unique("alice")
    _register_ws(ws_client, username=username)
    room_a = ws_client.post("/api/rooms", json={"name": _unique("general")}).json()
    room_b = ws_client.post("/api/rooms", json={"name": _unique("random")}).json()

    with ws_client.websocket_connect("/ws/chat") as ws:
        ws.send_json({"type": "join", "room_id": room_a["id"]})
        assert _recv(ws)["type"] == "joined"
        message = _send_and_sync(ws, room_a["id"], f"see #{room_b['name']} for details")

    assert _referenced_room_ids(ws_client, message["id"]) == {room_b["id"]}


def test_room_reference_to_room_sender_is_not_in_is_not_stored(ws_client_factory):
    instance1 = ws_client_factory()
    instance2 = ws_client_factory()

    _register_ws(instance1, _unique("alice"))
    room_a = instance1.post("/api/rooms", json={"name": _unique("general")}).json()

    _register_ws(instance2, _unique("bob"))
    other_room = instance2.post("/api/rooms", json={"name": _unique("bobs-room")}).json()
    # Deliberately not joining other_room from instance1.

    with instance1.websocket_connect("/ws/chat") as ws:
        ws.send_json({"type": "join", "room_id": room_a["id"]})
        assert _recv(ws)["type"] == "joined"
        message = _send_and_sync(ws, room_a["id"], f"check #{other_room['name']} sometime")

    assert _referenced_room_ids(instance1, message["id"]) == set()


def test_room_reference_inside_code_span_is_not_stored(ws_client):
    username = _unique("alice")
    _register_ws(ws_client, username=username)
    room_a = ws_client.post("/api/rooms", json={"name": _unique("general")}).json()
    room_b = ws_client.post("/api/rooms", json={"name": _unique("random")}).json()

    with ws_client.websocket_connect("/ws/chat") as ws:
        ws.send_json({"type": "join", "room_id": room_a["id"]})
        assert _recv(ws)["type"] == "joined"
        message = _send_and_sync(ws, room_a["id"], f"like this: `#{room_b['name']}`")

    assert _referenced_room_ids(ws_client, message["id"]) == set()


def test_room_reference_without_space_does_not_render_as_heading():
    # #47: confirms the char-class match itself is unaffected by CommonMark
    # heading syntax concerns (a real heading needs "# text" with a space --
    # this is a backend-extraction test, not a markdown-rendering one, but
    # asserts the regex matches "#roomname" with no space, which is the
    # whole point of the feature).
    from app.services.room_reference_service import ROOM_REFERENCE_PATTERN

    assert ROOM_REFERENCE_PATTERN.findall("check #general now") == ["general"]
    assert ROOM_REFERENCE_PATTERN.findall("# general now") == []
