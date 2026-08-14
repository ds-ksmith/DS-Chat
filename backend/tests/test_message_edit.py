import uuid

from app.schemas.user import UserCreate
from app.services.auth_service import register_user


def _unique(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


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


def test_ws_edit_updates_content_and_broadcasts(ws_client):
    username = _unique("alice")
    _register_ws(ws_client, username=username)
    room = ws_client.post("/api/rooms", json={"name": _unique("general")}).json()

    with ws_client.websocket_connect("/ws/chat") as ws:
        ws.send_json({"type": "join", "room_id": room["id"]})
        assert ws.receive_json()["type"] == "joined"

        ws.send_json({"type": "message", "room_id": room["id"], "content": "hello"})
        message = ws.receive_json()
        assert message["edited_at"] is None

        ws.send_json(
            {
                "type": "edit",
                "room_id": room["id"],
                "message_id": message["id"],
                "content": "hello, edited",
            }
        )
        update = ws.receive_json()
        assert update["type"] == "message_update"
        assert update["id"] == message["id"]
        assert update["content"] == "hello, edited"
        assert update["edited_at"] is not None

    resp = ws_client.get(f"/api/rooms/{room['id']}/messages")
    history = resp.json()
    edited = next(m for m in history if m["id"] == message["id"])
    assert edited["content"] == "hello, edited"
    assert edited["edited_at"] is not None


def test_ws_edit_rejects_non_author(ws_client):
    alice = _register_ws(ws_client, username=_unique("alice"))
    room = ws_client.post("/api/rooms", json={"name": _unique("general")}).json()

    bob = _register_ws(ws_client, username=_unique("bob"))
    ws_client.post(f"/api/rooms/{room['id']}/join")

    ws_client.post(
        "/api/auth/login", json={"username_or_email": alice["username"], "password": "password123"}
    )
    with ws_client.websocket_connect("/ws/chat") as alice_ws:
        alice_ws.send_json({"type": "join", "room_id": room["id"]})
        assert alice_ws.receive_json()["type"] == "joined"
        alice_ws.send_json({"type": "message", "room_id": room["id"], "content": "hello"})
        message = alice_ws.receive_json()

        ws_client.post(
            "/api/auth/login",
            json={"username_or_email": bob["username"], "password": "password123"},
        )
        with ws_client.websocket_connect("/ws/chat") as bob_ws:
            bob_ws.send_json({"type": "join", "room_id": room["id"]})
            assert bob_ws.receive_json()["type"] == "joined"
            bob_ws.send_json(
                {
                    "type": "edit",
                    "room_id": room["id"],
                    "message_id": message["id"],
                    "content": "hacked",
                }
            )
            resp = bob_ws.receive_json()
            assert resp["type"] == "error"
            assert "own messages" in resp["detail"]


def test_edit_fans_out_across_instances(ws_client_factory):
    instance1 = ws_client_factory()
    instance2 = ws_client_factory()

    alice = _register_ws(instance1, _unique("alice"))
    room = instance1.post("/api/rooms", json={"name": _unique("general")}).json()

    bob = _register_ws(instance2, _unique("bob"))
    instance2.post(f"/api/rooms/{room['id']}/join")

    with instance2.websocket_connect("/ws/chat") as bob_ws:
        bob_ws.send_json({"type": "join", "room_id": room["id"]})
        assert bob_ws.receive_json()["type"] == "joined"

        with instance1.websocket_connect("/ws/chat") as alice_ws:
            alice_ws.send_json({"type": "join", "room_id": room["id"]})
            assert alice_ws.receive_json()["type"] == "joined"
            alice_ws.send_json({"type": "message", "room_id": room["id"], "content": "hi"})
            message = alice_ws.receive_json()
            assert bob_ws.receive_json()["type"] == "message"

            alice_ws.send_json(
                {
                    "type": "edit",
                    "room_id": room["id"],
                    "message_id": message["id"],
                    "content": "hi, edited",
                }
            )
            assert alice_ws.receive_json()["type"] == "message_update"

            update = bob_ws.receive_json()
            assert update["type"] == "message_update"
            assert update["content"] == "hi, edited"
