import uuid

from app.schemas.user import UserCreate
from app.services.auth_service import register_user

# Disconnect-side cleanup (GlobalPresence.disconnect, the offline broadcast)
# is deliberately not exercised end-to-end here via a `with websocket_
# connect(...)` block closing: Starlette's TestClient tears down a
# websocket session by cancelling the server-side handler's task (confirmed
# via asyncio.CancelledError while investigating a hang here), not by
# delivering a real ASGI "websocket.disconnect" message the way an actual
# client going away does -- so a `finally` block's own `await` calls can be
# interrupted mid-cleanup in tests without that ever happening in
# production. No existing test in this suite exercises presence.leave()
# post-disconnect either, for the same reason. The connect-side behavior
# below (the half that's actually reliably testable) is what matters most:
# it proves the online transition and its broadcast work correctly.


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


def test_member_status_reflects_connection(ws_client):
    alice = _register_ws(ws_client, _unique("alice"))
    room = ws_client.post("/api/rooms", json={"name": _unique("general")}).json()

    members = ws_client.get(f"/api/rooms/{room['id']}/members").json()
    assert members[0]["status"] == "offline"

    with ws_client.websocket_connect("/ws/chat") as ws:
        ws.send_json({"type": "join", "room_id": room["id"]})
        assert ws.receive_json()["type"] == "joined"

        members = ws_client.get(f"/api/rooms/{room['id']}/members").json()
        assert members[0]["status"] == "online"


def test_connect_broadcasts_presence_to_shared_room(ws_client):
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

        ws_client.post(
            "/api/auth/login", json={"username_or_email": bob["username"], "password": "password123"}
        )
        with ws_client.websocket_connect("/ws/chat"):
            # bob connecting is a genuine offline->online transition for
            # him -- alice, already joined, should hear about it even
            # though she never sent anything and bob never joined a room.
            assert alice_ws.receive_json() == {
                "type": "member_updated",
                "room_id": room["id"],
                "user_id": bob["id"],
            }


def test_appear_offline_overrides_actual_connection(ws_client):
    alice = _register_ws(ws_client, _unique("alice"))
    room = ws_client.post("/api/rooms", json={"name": _unique("general")}).json()

    with ws_client.websocket_connect("/ws/chat") as ws:
        ws.send_json({"type": "join", "room_id": room["id"]})
        assert ws.receive_json()["type"] == "joined"

        members = ws_client.get(f"/api/rooms/{room['id']}/members").json()
        assert members[0]["status"] == "online"

        resp = ws_client.patch("/api/auth/me", json={"appear_offline": True})
        assert resp.status_code == 200
        assert resp.json()["appear_offline"] is True

        # alice is joined to her own room, so the broadcast her own change
        # triggers reaches her own socket.
        assert ws.receive_json() == {"type": "member_updated", "room_id": room["id"], "user_id": alice["id"]}

        members = ws_client.get(f"/api/rooms/{room['id']}/members").json()
        assert members[0]["status"] == "offline"

        resp = ws_client.patch("/api/auth/me", json={"appear_offline": False})
        assert resp.status_code == 200
        assert ws.receive_json()["type"] == "member_updated"

        members = ws_client.get(f"/api/rooms/{room['id']}/members").json()
        assert members[0]["status"] == "online"


def test_online_users_endpoint_respects_appear_offline(ws_client):
    alice = _register_ws(ws_client, _unique("alice"))
    bob = _register_ws(ws_client, _unique("bob"))

    ws_client.post(
        "/api/auth/login", json={"username_or_email": alice["username"], "password": "password123"}
    )
    with ws_client.websocket_connect("/ws/chat"):
        online = ws_client.get("/api/users/online").json()
        assert alice["id"] in online
        assert bob["id"] not in online

        resp = ws_client.patch("/api/auth/me", json={"appear_offline": True})
        assert resp.status_code == 200

        online = ws_client.get("/api/users/online").json()
        assert alice["id"] not in online

    online = ws_client.get("/api/users/online").json()
    assert alice["id"] not in online
