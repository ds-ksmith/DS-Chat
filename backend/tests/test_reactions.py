import uuid

from app.models import User
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


def _make_admin_ws(ws_client, user_id: str) -> None:
    async def _promote():
        async with ws_client.session_factory() as session:
            user = await session.get(User, uuid.UUID(user_id))
            user.is_site_admin = True
            await session.commit()

    ws_client.portal.call(_promote)


def test_ws_reaction_toggle_add(ws_client):
    _register_ws(ws_client, _unique("alice"))
    room = ws_client.post("/api/rooms", json={"name": _unique("general")}).json()

    with ws_client.websocket_connect("/ws/chat") as ws:
        ws.send_json({"type": "join", "room_id": room["id"]})
        assert ws.receive_json()["type"] == "joined"
        ws.send_json({"type": "message", "room_id": room["id"], "content": "hello"})
        message = ws.receive_json()
        assert message["reactions"] == []

        ws.send_json({"type": "reaction", "room_id": room["id"], "message_id": message["id"], "emoji": "👍"})
        update = ws.receive_json()
        assert update["type"] == "reaction_update"
        assert update["id"] == message["id"]
        assert len(update["reactions"]) == 1
        assert update["reactions"][0]["emoji"] == "👍"
        assert update["reactions"][0]["count"] == 1


def test_ws_reaction_toggle_remove(ws_client):
    alice = _register_ws(ws_client, _unique("alice"))
    room = ws_client.post("/api/rooms", json={"name": _unique("general")}).json()

    with ws_client.websocket_connect("/ws/chat") as ws:
        ws.send_json({"type": "join", "room_id": room["id"]})
        assert ws.receive_json()["type"] == "joined"
        ws.send_json({"type": "message", "room_id": room["id"], "content": "hello"})
        message = ws.receive_json()

        ws.send_json({"type": "reaction", "room_id": room["id"], "message_id": message["id"], "emoji": "👍"})
        first = ws.receive_json()
        assert len(first["reactions"]) == 1

        ws.send_json({"type": "reaction", "room_id": room["id"], "message_id": message["id"], "emoji": "👍"})
        second = ws.receive_json()
        assert second["reactions"] == []


def test_reaction_appears_in_rest_message_list(ws_client):
    _register_ws(ws_client, _unique("alice"))
    room = ws_client.post("/api/rooms", json={"name": _unique("general")}).json()

    with ws_client.websocket_connect("/ws/chat") as ws:
        ws.send_json({"type": "join", "room_id": room["id"]})
        assert ws.receive_json()["type"] == "joined"
        ws.send_json({"type": "message", "room_id": room["id"], "content": "hello"})
        message = ws.receive_json()
        ws.send_json({"type": "reaction", "room_id": room["id"], "message_id": message["id"], "emoji": "🔥"})
        assert ws.receive_json()["type"] == "reaction_update"

    history = ws_client.get(f"/api/rooms/{room['id']}/messages").json()
    persisted = next(m for m in history if m["id"] == message["id"])
    assert persisted["reactions"] == [{"emoji": "🔥", "count": 1, "user_ids": [message["user_id"]]}]


def test_reaction_broadcasts_to_other_room_members(ws_client):
    alice = _register_ws(ws_client, _unique("alice"))
    room = ws_client.post("/api/rooms", json={"name": _unique("general")}).json()

    bob = _register_ws(ws_client, _unique("bob"))
    ws_client.post(f"/api/rooms/{room['id']}/join")

    ws_client.post(
        "/api/auth/login", json={"username_or_email": alice["username"], "password": "password123"}
    )
    with ws_client.websocket_connect("/ws/chat") as alice_ws:
        alice_ws.send_json({"type": "join", "room_id": room["id"]})
        assert alice_ws.receive_json()["type"] == "joined"
        alice_ws.send_json({"type": "message", "room_id": room["id"], "content": "hi"})
        message = alice_ws.receive_json()

        ws_client.post(
            "/api/auth/login", json={"username_or_email": bob["username"], "password": "password123"}
        )
        with ws_client.websocket_connect("/ws/chat") as bob_ws:
            bob_ws.send_json({"type": "join", "room_id": room["id"]})
            assert bob_ws.receive_json()["type"] == "joined"

            ws_client.post(
                "/api/auth/login",
                json={"username_or_email": alice["username"], "password": "password123"},
            )
            alice_ws.send_json(
                {"type": "reaction", "room_id": room["id"], "message_id": message["id"], "emoji": "🎉"}
            )
            assert alice_ws.receive_json()["type"] == "reaction_update"
            update = bob_ws.receive_json()
            assert update["type"] == "reaction_update"
            assert update["reactions"][0]["emoji"] == "🎉"


def test_reaction_requires_room_membership(ws_client_factory):
    owner_client = ws_client_factory()
    outsider_client = ws_client_factory()

    _register_ws(owner_client, _unique("alice"))
    room = owner_client.post("/api/rooms", json={"name": _unique("general")}).json()

    with owner_client.websocket_connect("/ws/chat") as owner_ws:
        owner_ws.send_json({"type": "join", "room_id": room["id"]})
        assert owner_ws.receive_json()["type"] == "joined"
        owner_ws.send_json({"type": "message", "room_id": room["id"], "content": "hello"})
        message = owner_ws.receive_json()

    _register_ws(outsider_client, _unique("mallory"))
    with outsider_client.websocket_connect("/ws/chat") as outsider_ws:
        outsider_ws.send_json(
            {"type": "reaction", "room_id": room["id"], "message_id": message["id"], "emoji": "👍"}
        )
        resp = outsider_ws.receive_json()
        assert resp["type"] == "error"


def test_bot_reaction_without_write_scope_rejected(ws_client_factory):
    ws_client = ws_client_factory()
    admin = _register_ws(ws_client, _unique("admin"))
    _make_admin_ws(ws_client, admin["id"])
    room = ws_client.post("/api/rooms", json={"name": _unique("general")}).json()

    with ws_client.websocket_connect("/ws/chat") as ws:
        ws.send_json({"type": "join", "room_id": room["id"]})
        assert ws.receive_json()["type"] == "joined"
        ws.send_json({"type": "message", "room_id": room["id"], "content": "hello"})
        message = ws.receive_json()

    bot = ws_client.post("/api/admin/bots", json={"username": _unique("bot")}).json()
    token = ws_client.post(
        f"/api/admin/bots/{bot['id']}/tokens", json={"scopes": ["read:messages"]}
    ).json()["token"]
    ws_client.post(f"/api/rooms/{room['id']}/join", headers={"Authorization": f"Bearer {token}"})

    with ws_client.websocket_connect("/ws/chat", headers={"Authorization": f"Bearer {token}"}) as bot_ws:
        bot_ws.send_json({"type": "join", "room_id": room["id"]})
        assert bot_ws.receive_json()["type"] == "joined"
        bot_ws.send_json(
            {"type": "reaction", "room_id": room["id"], "message_id": message["id"], "emoji": "👍"}
        )
        resp = bot_ws.receive_json()
        assert resp["type"] == "error"
        assert "write:messages" in resp["detail"]


def test_reaction_empty_emoji_rejected(ws_client):
    _register_ws(ws_client, _unique("alice"))
    room = ws_client.post("/api/rooms", json={"name": _unique("general")}).json()

    with ws_client.websocket_connect("/ws/chat") as ws:
        ws.send_json({"type": "join", "room_id": room["id"]})
        assert ws.receive_json()["type"] == "joined"
        ws.send_json({"type": "message", "room_id": room["id"], "content": "hello"})
        message = ws.receive_json()

        ws.send_json({"type": "reaction", "room_id": room["id"], "message_id": message["id"], "emoji": ""})
        resp = ws.receive_json()
        assert resp["type"] == "error"


def test_reaction_invalid_message_id_rejected(ws_client):
    _register_ws(ws_client, _unique("alice"))
    room = ws_client.post("/api/rooms", json={"name": _unique("general")}).json()

    with ws_client.websocket_connect("/ws/chat") as ws:
        ws.send_json({"type": "join", "room_id": room["id"]})
        assert ws.receive_json()["type"] == "joined"
        ws.send_json(
            {"type": "reaction", "room_id": room["id"], "message_id": str(uuid.uuid4()), "emoji": "👍"}
        )
        resp = ws.receive_json()
        assert resp["type"] == "error"
        assert "Message not found" in resp["detail"]


def test_reaction_wrong_room_rejected(ws_client):
    _register_ws(ws_client, _unique("alice"))
    room_a = ws_client.post("/api/rooms", json={"name": _unique("room-a")}).json()
    room_b = ws_client.post("/api/rooms", json={"name": _unique("room-b")}).json()

    with ws_client.websocket_connect("/ws/chat") as ws:
        ws.send_json({"type": "join", "room_id": room_a["id"]})
        assert ws.receive_json()["type"] == "joined"
        ws.send_json({"type": "message", "room_id": room_a["id"], "content": "hello"})
        message = ws.receive_json()

        ws.send_json({"type": "join", "room_id": room_b["id"]})
        assert ws.receive_json()["type"] == "joined"
        ws.send_json(
            {"type": "reaction", "room_id": room_b["id"], "message_id": message["id"], "emoji": "👍"}
        )
        resp = ws.receive_json()
        assert resp["type"] == "error"
        assert "Message not found" in resp["detail"]
