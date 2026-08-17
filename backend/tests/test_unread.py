import uuid

from tests.conftest import register_and_login


def _unique(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _recv(ws) -> dict:
    """Reads the next frame, discarding member_updated presence-change
    broadcasts -- another connection going online/offline is real, expected
    noise these tests aren't about."""
    while True:
        msg = ws.receive_json()
        if msg.get("type") != "member_updated":
            return msg


def _register_ws(ws_client, username: str) -> dict:
    from app.schemas.user import UserCreate
    from app.services.auth_service import register_user

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


def _has_unread(rooms: list[dict], room_id: str) -> bool:
    return next(r for r in rooms if r["id"] == room_id)["has_unread"]


def _send_and_sync(ws, room_id: str, content: str) -> dict:
    """Sends a message and waits for its ack, then a sync barrier: the WS
    handler processes frames strictly sequentially, so an ack for a second,
    idempotent "join" only arrives once the message frame's *full* handling
    -- including the offline-member notify step this feature hooks into --
    has actually finished. Without this, the message's own ack (itself just
    a mid-handler side effect, not the handler's return) proves nothing
    about whether _notify_offline_members has run yet, and closing the
    sender's socket right after that ack can cancel that still-in-flight
    work (mirrors the same "sync barrier" pattern in test_broadcast.py)."""
    ws.send_json({"type": "message", "room_id": room_id, "content": content})
    message = ws.receive_json()
    ws.send_json({"type": "join", "room_id": room_id})
    assert ws.receive_json()["type"] == "joined"
    return message


def test_message_marks_room_unread_and_notifies_offline_member(ws_client_factory):
    instance1 = ws_client_factory()
    instance2 = ws_client_factory()

    alice = _register_ws(instance1, _unique("alice"))
    room = instance1.post("/api/rooms", json={"name": _unique("general")}).json()

    bob = _register_ws(instance2, _unique("bob"))
    instance2.post(f"/api/rooms/{room['id']}/join")

    # Bob is connected (so he can receive the per-user unread_update signal)
    # but never joins this room's channel -- exactly the "room isn't open"
    # case this feature exists for.
    with instance2.websocket_connect("/ws/chat") as bob_ws:
        with instance1.websocket_connect("/ws/chat") as alice_ws:
            alice_ws.send_json({"type": "join", "room_id": room["id"]})
            assert alice_ws.receive_json()["type"] == "joined"
            message = _send_and_sync(alice_ws, room["id"], "hi bob")
            assert message["type"] == "message"

        update = _recv(bob_ws)
        assert update == {"type": "unread_update", "room_id": room["id"]}

    bob_rooms = instance2.get("/api/rooms/mine").json()
    assert _has_unread(bob_rooms, room["id"]) is True

    alice_rooms = instance1.get("/api/rooms/mine").json()
    assert _has_unread(alice_rooms, room["id"]) is False


def test_no_unread_signal_for_member_with_room_joined(ws_client_factory):
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
            message = _send_and_sync(alice_ws, room["id"], "hi bob")
            assert message["type"] == "message"

        # Bob has this room's channel joined, so he gets the normal message
        # broadcast, not an unread_update -- he's actively watching. Alice's
        # sync-barrier "joined" ack (from _send_and_sync) is private to her
        # own connection, not broadcast, so bob sees nothing further here.
        #
        # Note: this only proves the real-time *signal* is suppressed for a
        # joined member. Persisted has_unread (GET /rooms/mine) is a
        # separate, client-driven mechanism (see test_mark_read_endpoint_
        # clears_unread) -- being joined to the channel doesn't by itself
        # advance last_read_at server-side; the frontend does that
        # explicitly whenever a message arrives while the room is both
        # joined and genuinely visible.
        update = _recv(bob_ws)
        assert update["type"] == "message"


def test_mark_read_endpoint_clears_unread(ws_client_factory):
    instance1 = ws_client_factory()
    instance2 = ws_client_factory()

    _register_ws(instance1, _unique("alice"))
    room = instance1.post("/api/rooms", json={"name": _unique("general")}).json()

    _register_ws(instance2, _unique("bob"))
    instance2.post(f"/api/rooms/{room['id']}/join")

    with instance1.websocket_connect("/ws/chat") as alice_ws:
        alice_ws.send_json({"type": "join", "room_id": room["id"]})
        assert alice_ws.receive_json()["type"] == "joined"
        message = _send_and_sync(alice_ws, room["id"], "hi bob")
        assert message["type"] == "message"

    assert _has_unread(instance2.get("/api/rooms/mine").json(), room["id"]) is True

    resp = instance2.post(f"/api/rooms/{room['id']}/read")
    assert resp.status_code == 204

    assert _has_unread(instance2.get("/api/rooms/mine").json(), room["id"]) is False


def test_joining_room_does_not_retroactively_mark_history_unread(ws_client_factory):
    instance1 = ws_client_factory()
    instance2 = ws_client_factory()

    _register_ws(instance1, _unique("alice"))
    room = instance1.post("/api/rooms", json={"name": _unique("general")}).json()

    with instance1.websocket_connect("/ws/chat") as alice_ws:
        alice_ws.send_json({"type": "join", "room_id": room["id"]})
        assert alice_ws.receive_json()["type"] == "joined"
        message = _send_and_sync(alice_ws, room["id"], "before bob joins")
        assert message["type"] == "message"

    _register_ws(instance2, _unique("bob"))
    instance2.post(f"/api/rooms/{room['id']}/join")

    assert _has_unread(instance2.get("/api/rooms/mine").json(), room["id"]) is False


async def test_mark_read_requires_room_membership(client, db_session):
    await register_and_login(client, db_session, username=_unique("alice"))
    room = (await client.post("/api/rooms", json={"name": _unique("general")})).json()

    await register_and_login(client, db_session, username=_unique("bob"))
    resp = await client.post(f"/api/rooms/{room['id']}/read")
    assert resp.status_code == 403
