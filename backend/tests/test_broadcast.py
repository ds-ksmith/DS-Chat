import uuid

from app.schemas.user import UserCreate
from app.services.auth_service import register_user


def _unique(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


_NOISE_TYPES = {"member_updated", "dm_presence_update"}


def _recv(ws) -> dict:
    """Reads the next frame, transparently discarding presence-change
    broadcasts (member_updated, and #63's dm_presence_update) -- another
    connection sharing a room or a DM going online/offline is real,
    expected noise these tests aren't about."""
    while True:
        msg = ws.receive_json()
        if msg.get("type") not in _NOISE_TYPES:
            return msg


def _fake_send_email(monkeypatch):
    calls = []

    async def fake(db, to, subject, paragraphs, **kwargs):
        calls.append({"to": to, "subject": subject, "paragraphs": paragraphs, **kwargs})

    monkeypatch.setattr("app.services.room_service.send_email", fake)
    return calls


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


def test_message_fans_out_across_instances(ws_client_factory):
    # Two independent app instances -- separate ConnectionManager, separate
    # Redis pubsub subscription, separate everything except the Postgres and
    # Redis they're both pointed at -- the same way two app-server processes
    # behind Nginx would be. Proves delivery actually crosses Redis, not
    # just in-process delivery within a single ConnectionManager.
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
            alice_ws.send_json(
                {"type": "message", "room_id": room["id"], "content": "hi from instance 1"}
            )
            assert alice_ws.receive_json()["type"] == "message"

            received = _recv(bob_ws)
            assert received["type"] == "message"
            assert received["content"] == "hi from instance 1"
            assert received["username"] == alice["username"]


def test_presence_is_shared_across_instances(ws_client_factory, monkeypatch):
    calls = []
    monkeypatch.setattr("app.services.push_service.webpush", lambda **kw: calls.append(kw))

    instance1 = ws_client_factory()
    instance2 = ws_client_factory()

    alice = _register_ws(instance1, _unique("alice"))
    room = instance1.post("/api/rooms", json={"name": _unique("general")}).json()

    bob = _register_ws(instance2, _unique("bob"))
    instance2.post(f"/api/rooms/{room['id']}/join")
    instance2.post(
        "/api/push/subscribe",
        json={
            "endpoint": f"https://push.example.com/ep-{bob['id']}",
            "keys": {"p256dh": "p256dh-bob", "auth": "auth-bob"},
        },
    )

    with instance2.websocket_connect("/ws/chat") as bob_ws:
        bob_ws.send_json({"type": "join", "room_id": room["id"]})
        assert bob_ws.receive_json()["type"] == "joined"

        with instance1.websocket_connect("/ws/chat") as alice_ws:
            alice_ws.send_json({"type": "join", "room_id": room["id"]})
            assert alice_ws.receive_json()["type"] == "joined"
            alice_ws.send_json({"type": "message", "room_id": room["id"], "content": "hi"})
            assert alice_ws.receive_json()["type"] == "message"

            # bob is connected -- just on the other instance -- so he should
            # get the broadcast via Redis, not a push notification. If
            # presence were still process-local (pre-phase-5 behavior) he'd
            # look offline to instance1 and get a redundant push.
            assert _recv(bob_ws)["type"] == "message"

            # Sync barrier: the handler processes frames strictly
            # sequentially, so a second (idempotent) join only acks once the
            # "message" frame's full handling -- including the offline-push
            # step -- has completed on instance1.
            alice_ws.send_json({"type": "join", "room_id": room["id"]})
            assert alice_ws.receive_json()["type"] == "joined"

    assert calls == []


def test_add_member_notifies_target_user_via_websocket(ws_client_factory, monkeypatch):
    # Bob is only ever "connected," never "joined" -- proving the room_added
    # signal reaches him on his own per-user channel, independent of (and
    # necessarily before) ever joining the room's own channel, which he
    # can't do until this signal tells his client the room exists at all.
    _fake_send_email(monkeypatch)

    instance1 = ws_client_factory()
    instance2 = ws_client_factory()

    alice = _register_ws(instance1, _unique("alice"))
    room = instance1.post("/api/rooms", json={"name": _unique("general")}).json()

    bob = _register_ws(instance2, _unique("bob"))

    with instance2.websocket_connect("/ws/chat") as bob_ws:
        resp = instance1.post(f"/api/rooms/{room['id']}/members", json={"user_id": bob["id"]})
        assert resp.status_code == 201, resp.text

        received = bob_ws.receive_json()
        assert received == {"type": "room_added", "room_id": room["id"]}


def test_start_dm_notifies_other_participant_via_websocket(ws_client_factory):
    # A production report: bob had no idea a DM existed until he reloaded --
    # find_or_create_dm was creating the room/membership correctly but never
    # sending this signal, unlike every other "you're now in a room" path
    # (add_member, above). Same shape as that test: bob is only ever
    # "connected," never "joined," proving the signal alone is what tells
    # his client the room exists at all.
    instance1 = ws_client_factory()
    instance2 = ws_client_factory()

    alice = _register_ws(instance1, _unique("alice"))
    bob = _register_ws(instance2, _unique("bob"))

    with instance2.websocket_connect("/ws/chat") as bob_ws:
        resp = instance1.post("/api/rooms/dm", json={"other_user_id": bob["id"]})
        assert resp.status_code == 201, resp.text
        room = resp.json()

        received = bob_ws.receive_json()
        assert received == {"type": "room_added", "room_id": room["id"]}


def test_new_message_notifies_recipient_who_hid_the_dm_via_websocket(ws_client_factory):
    # A second production report on the same underlying gap: hiding a DM
    # correctly clears out of GET /rooms/mine, but when the other person
    # messages again, the *only* existing signal for that (unread_update)
    # does `setRooms(prev => prev.map(...))` -- a no-op for a room that
    # isn't in `prev` at all, which a hidden DM by definition isn't. Needs
    # the same room_added signal a brand new DM gets, not just a DB-level
    # un-hide.
    instance1 = ws_client_factory()
    instance2 = ws_client_factory()

    alice = _register_ws(instance1, _unique("alice"))
    bob = _register_ws(instance2, _unique("bob"))

    room = instance1.post("/api/rooms/dm", json={"other_user_id": bob["id"]}).json()
    resp = instance2.post(f"/api/rooms/{room['id']}/hide")
    assert resp.status_code == 204

    with instance2.websocket_connect("/ws/chat") as bob_ws:
        with instance1.websocket_connect("/ws/chat") as alice_ws:
            alice_ws.send_json({"type": "join", "room_id": room["id"]})
            assert alice_ws.receive_json()["type"] == "joined"
            alice_ws.send_json({"type": "message", "room_id": room["id"], "content": "you there?"})
            alice_ws.receive_json()
            # Sync barrier (see test_mentions.py's identical helper): the
            # message ack only proves the room-level broadcast happened,
            # not that broadcast_new_message's own continuation (which
            # un-hides the room and publishes room_added) has finished --
            # a second frame's own ack proves that before this connection
            # closes underneath it.
            alice_ws.send_json({"type": "join", "room_id": room["id"]})
            assert alice_ws.receive_json()["type"] == "joined"

        received = _recv(bob_ws)
        assert received == {"type": "room_added", "room_id": room["id"]}


def test_profile_update_notifies_room_members_via_websocket(ws_client_factory, monkeypatch):
    # Only reaches clients that have the room's own channel joined --
    # exactly the case where a stale avatar/display name would actually be
    # visible on screen (a room the user has open right now).
    _fake_send_email(monkeypatch)

    instance1 = ws_client_factory()
    instance2 = ws_client_factory()

    alice = _register_ws(instance1, _unique("alice"))
    room = instance1.post("/api/rooms", json={"name": _unique("general")}).json()

    bob = _register_ws(instance2, _unique("bob"))
    instance2.post(f"/api/rooms/{room['id']}/join")

    with instance2.websocket_connect("/ws/chat") as bob_ws:
        bob_ws.send_json({"type": "join", "room_id": room["id"]})
        assert bob_ws.receive_json()["type"] == "joined"

        resp = instance1.patch("/api/auth/me", json={"display_name": "Alice Updated"})
        assert resp.status_code == 200, resp.text

        received = bob_ws.receive_json()
        assert received == {"type": "member_updated", "room_id": room["id"], "user_id": alice["id"]}
