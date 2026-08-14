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


def test_ws_message_without_join_errors(ws_client):
    _register(ws_client, username=_unique("alice"))
    room = ws_client.post("/api/rooms", json={"name": _unique("general")}).json()

    with ws_client.websocket_connect("/ws/chat") as ws:
        ws.send_json({"type": "message", "room_id": room["id"], "content": "hello"})
        resp = ws.receive_json()
        assert resp["type"] == "error"
