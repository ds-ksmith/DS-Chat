import uuid

from starlette.websockets import WebSocketDisconnect

from app.schemas.user import UserCreate
from app.services.auth_service import register_user
from app.ws.chat import WS_UNAUTHENTICATED


def _unique(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _register(ws_client, username):
    # No public register endpoint (invite-only site): seed the user directly
    # via the ws_client's own session factory (see conftest.ws_client), then
    # log in through the real endpoint to get a session cookie.
    async def _seed():
        async with ws_client.session_factory() as session:
            await register_user(
                session,
                UserCreate(username=username, email=f"{username}@example.com", password="password123"),
            )

    ws_client.portal.call(_seed)

    resp = ws_client.post(
        "/api/auth/login",
        json={"username_or_email": username, "password": "password123"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_ws_requires_auth(ws_client):
    try:
        with ws_client.websocket_connect("/ws/chat"):
            pass
        assert False, "expected the connection to be rejected"
    except WebSocketDisconnect as exc:
        assert exc.code == WS_UNAUTHENTICATED


def test_ws_join_and_message_roundtrip(ws_client):
    username = _unique("alice")
    _register(ws_client, username=username)
    room = ws_client.post("/api/rooms", json={"name": _unique("general")}).json()

    with ws_client.websocket_connect("/ws/chat") as ws:
        ws.send_json({"type": "join", "room_id": room["id"]})
        joined = ws.receive_json()
        assert joined == {"type": "joined", "room_id": room["id"]}

        ws.send_json({"type": "message", "room_id": room["id"], "content": "hello"})
        message = ws.receive_json()
        assert message["type"] == "message"
        assert message["content"] == "hello"
        assert message["room_id"] == room["id"]
        assert message["username"] == username

    resp = ws_client.get(f"/api/rooms/{room['id']}/messages")
    assert resp.status_code == 200
    history = resp.json()
    assert any(m["content"] == "hello" and m["username"] == username for m in history)


def test_history_tiebreaks_identical_timestamps_by_id(ws_client):
    # Two messages sharing the exact same created_at (a real possibility --
    # rapid sends, a webhook, microsecond-precision collisions under load)
    # must still come back in a single, stable order every call, not
    # whatever order Postgres feels like giving ties with no secondary sort
    # key -- see list_recent_messages's order_by comment.
    username = _unique("alice")
    _register(ws_client, username=username)
    room = ws_client.post("/api/rooms", json={"name": _unique("general")}).json()

    with ws_client.websocket_connect("/ws/chat") as ws:
        ws.send_json({"type": "join", "room_id": room["id"]})
        assert ws.receive_json()["type"] == "joined"
        ws.send_json({"type": "message", "room_id": room["id"], "content": "first"})
        first = ws.receive_json()
        ws.send_json({"type": "message", "room_id": room["id"], "content": "second"})
        second = ws.receive_json()

    async def _force_same_timestamp():
        from sqlalchemy import select

        from app.models import Message

        async with ws_client.session_factory() as session:
            result = await session.execute(
                select(Message).where(Message.id.in_([uuid.UUID(first["id"]), uuid.UUID(second["id"])]))
            )
            rows = {str(m.id): m for m in result.scalars().all()}
            rows[first["id"]].created_at = rows[second["id"]].created_at
            await session.commit()

    ws_client.portal.call(_force_same_timestamp)

    resp = ws_client.get(f"/api/rooms/{room['id']}/messages")
    assert resp.status_code == 200
    history = [m for m in resp.json() if m["content"] in ("first", "second")]
    assert len(history) == 2

    # order_by(created_at.desc(), id.desc()) then reversed for display --
    # with a tied created_at, the higher id (whichever message that is)
    # must consistently render second.
    expected_order = sorted([first, second], key=lambda m: m["id"])
    assert [m["content"] for m in history] == [m["content"] for m in expected_order]


def test_ws_sends_heartbeat_ping(ws_client, monkeypatch):
    # #76: with nothing else sent on the connection, a "ping" must arrive
    # proactively once the idle timeout elapses -- shrunk here so the test
    # doesn't actually wait the real 30s. Replying "pong" (the frontend's
    # own behavior) must be accepted silently and leave the connection
    # fully usable afterward, not treated as an unknown message type.
    monkeypatch.setattr("app.ws.chat.WS_PING_INTERVAL_SECONDS", 0.05)
    username = _unique("alice")
    _register(ws_client, username=username)
    room = ws_client.post("/api/rooms", json={"name": _unique("general")}).json()

    with ws_client.websocket_connect("/ws/chat") as ws:
        assert ws.receive_json() == {"type": "ping"}
        ws.send_json({"type": "pong"})
        ws.send_json({"type": "join", "room_id": room["id"]})
        assert ws.receive_json() == {"type": "joined", "room_id": room["id"]}


def test_ws_message_without_join_errors(ws_client):
    _register(ws_client, username=_unique("alice"))
    room = ws_client.post("/api/rooms", json={"name": _unique("general")}).json()

    with ws_client.websocket_connect("/ws/chat") as ws:
        ws.send_json({"type": "message", "room_id": room["id"], "content": "hello"})
        resp = ws.receive_json()
        assert resp["type"] == "error"
