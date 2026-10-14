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


# --- #77: liveness -----------------------------------------------------------
# A connection that stops answering the app-level heartbeat is dropped by the
# server, and a connection that does answer keeps its presence entry renewed.
# Timings are shrunk so nothing here waits on the real 30s/90s values.


def _fast_heartbeat(monkeypatch):
    monkeypatch.setattr("app.ws.chat.WS_PING_INTERVAL_SECONDS", 0.05)
    monkeypatch.setattr("app.ws.chat.WS_DEAD_AFTER_SECONDS", 0.2)
    monkeypatch.setattr("app.ws.chat.PRESENCE_REFRESH_MIN_INTERVAL_SECONDS", 0)


def test_unresponsive_client_is_disconnected_by_the_server(ws_client, monkeypatch):
    # The frozen-page / sleeping-laptop case: the transport stays open (the
    # browser answers protocol pings itself) but the page never replies to
    # the app-level ping.
    from starlette.websockets import WebSocketDisconnect

    _fast_heartbeat(monkeypatch)
    _register_ws(ws_client, _unique("alice"))

    with ws_client.websocket_connect("/ws/chat") as ws:
        pings = 0
        try:
            while True:
                assert ws.receive_json() == {"type": "ping"}
                pings += 1
                assert pings < 100, "server never gave up on a silent client"
        except WebSocketDisconnect as exc:
            assert exc.code == 4408
        assert pings >= 2


def test_client_that_answers_pings_is_not_disconnected(ws_client, monkeypatch):
    _fast_heartbeat(monkeypatch)
    _register_ws(ws_client, _unique("alice"))
    room = ws_client.post("/api/rooms", json={"name": _unique("general")}).json()

    with ws_client.websocket_connect("/ws/chat") as ws:
        # Far longer than WS_DEAD_AFTER_SECONDS in total.
        for _ in range(12):
            assert ws.receive_json() == {"type": "ping"}
            ws.send_json({"type": "pong"})
        ws.send_json({"type": "join", "room_id": room["id"]})
        while (msg := ws.receive_json())["type"] == "ping":
            pass
        assert msg == {"type": "joined", "room_id": room["id"]}


def test_bot_connection_is_not_dropped_for_ignoring_pings(ws_client_factory, monkeypatch):
    # API-token clients aren't expected to speak the app heartbeat.
    _fast_heartbeat(monkeypatch)
    ws_client = ws_client_factory()
    admin = _register_ws(ws_client, _unique("admin"))

    async def _promote():
        from app.models import User

        async with ws_client.session_factory() as session:
            user = await session.get(User, uuid.UUID(admin["id"]))
            user.is_site_admin = True
            await session.commit()

    ws_client.portal.call(_promote)
    room = ws_client.post("/api/rooms", json={"name": _unique("general")}).json()
    bot = ws_client.post("/api/admin/bots", json={"username": _unique("bot")}).json()
    token = ws_client.post(
        f"/api/admin/bots/{bot['id']}/tokens", json={"scopes": ["read:messages", "write:messages"]}
    ).json()["token"]
    ws_client.post(f"/api/rooms/{room['id']}/join", headers={"Authorization": f"Bearer {token}"})

    with ws_client.websocket_connect("/ws/chat", headers={"Authorization": f"Bearer {token}"}) as ws:
        for _ in range(8):  # ~0.4s of silence, twice WS_DEAD_AFTER_SECONDS
            assert ws.receive_json() == {"type": "ping"}
        ws.send_json({"type": "join", "room_id": room["id"]})
        while (msg := ws.receive_json())["type"] == "ping":
            pass
        assert msg["type"] == "joined"


def test_presence_entry_is_renewed_while_the_client_answers(ws_client, monkeypatch):
    import time

    _fast_heartbeat(monkeypatch)
    alice = _register_ws(ws_client, _unique("alice"))

    async def _scores():
        redis = ws_client.app.state.redis
        return await redis.zrange("presence:v2:global", 0, -1, withscores=True)

    with ws_client.websocket_connect("/ws/chat") as ws:
        # Wait for the first ping so the connect-time entry exists.
        assert ws.receive_json() == {"type": "ping"}
        first = [s for m, s in ws_client.portal.call(_scores) if m.startswith(alice["id"])]
        assert len(first) == 1

        time.sleep(0.1)
        ws.send_json({"type": "pong"})
        # Any later frame arriving back proves the pong was processed.
        while ws.receive_json()["type"] != "ping":
            pass
        second = [s for m, s in ws_client.portal.call(_scores) if m.startswith(alice["id"])]
        assert second and second[0] > first[0]
