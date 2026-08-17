import uuid


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


def _has_mention(rooms: list[dict], room_id: str) -> bool:
    return next(r for r in rooms if r["id"] == room_id)["has_mention"]


def _send_and_sync(ws, room_id: str, content: str) -> dict:
    """See test_unread.py's identical helper -- a sync barrier so the
    message frame's full handling (including the offline-notify step this
    feature hooks into) is guaranteed complete before checking anything."""
    ws.send_json({"type": "message", "room_id": room_id, "content": content})
    message = ws.receive_json()
    ws.send_json({"type": "join", "room_id": room_id})
    assert ws.receive_json()["type"] == "joined"
    return message


def test_mention_notifies_only_the_mentioned_offline_member(ws_client_factory):
    instance1 = ws_client_factory()
    instance2 = ws_client_factory()
    instance3 = ws_client_factory()

    alice = _register_ws(instance1, _unique("alice"))
    room = instance1.post("/api/rooms", json={"name": _unique("general")}).json()

    bob = _register_ws(instance2, _unique("bob"))
    instance2.post(f"/api/rooms/{room['id']}/join")

    carol = _register_ws(instance3, _unique("carol"))
    instance3.post(f"/api/rooms/{room['id']}/join")

    with instance2.websocket_connect("/ws/chat") as bob_ws, instance3.websocket_connect(
        "/ws/chat"
    ) as carol_ws:
        with instance1.websocket_connect("/ws/chat") as alice_ws:
            alice_ws.send_json({"type": "join", "room_id": room["id"]})
            assert alice_ws.receive_json()["type"] == "joined"
            message = _send_and_sync(alice_ws, room["id"], f"hey @{bob['username']}, look at this")
            assert message["type"] == "message"

        bob_update = _recv(bob_ws)
        assert bob_update == {"type": "unread_update", "room_id": room["id"], "mentioned": True}

        carol_update = _recv(carol_ws)
        assert carol_update == {"type": "unread_update", "room_id": room["id"], "mentioned": False}

    bob_rooms = instance2.get("/api/rooms/mine").json()
    assert _has_mention(bob_rooms, room["id"]) is True

    carol_rooms = instance3.get("/api/rooms/mine").json()
    assert _has_mention(carol_rooms, room["id"]) is False


def test_mention_of_non_member_is_not_a_mention(ws_client_factory):
    instance1 = ws_client_factory()
    instance2 = ws_client_factory()

    alice = _register_ws(instance1, _unique("alice"))
    room = instance1.post("/api/rooms", json={"name": _unique("general")}).json()

    _register_ws(instance2, _unique("bob"))
    instance2.post(f"/api/rooms/{room['id']}/join")

    with instance1.websocket_connect("/ws/chat") as alice_ws:
        alice_ws.send_json({"type": "join", "room_id": room["id"]})
        assert alice_ws.receive_json()["type"] == "joined"
        message = _send_and_sync(alice_ws, room["id"], "hey @nobody-by-this-name, anyone home?")
        assert message["type"] == "message"

    assert _has_mention(instance2.get("/api/rooms/mine").json(), room["id"]) is False


def test_mention_inside_code_span_is_not_a_mention(ws_client_factory):
    instance1 = ws_client_factory()
    instance2 = ws_client_factory()

    alice = _register_ws(instance1, _unique("alice"))
    room = instance1.post("/api/rooms", json={"name": _unique("general")}).json()

    bob = _register_ws(instance2, _unique("bob"))
    instance2.post(f"/api/rooms/{room['id']}/join")

    with instance1.websocket_connect("/ws/chat") as alice_ws:
        alice_ws.send_json({"type": "join", "room_id": room["id"]})
        assert alice_ws.receive_json()["type"] == "joined"
        message = _send_and_sync(alice_ws, room["id"], f"check this out: `@{bob['username']}`")
        assert message["type"] == "message"

    assert _has_mention(instance2.get("/api/rooms/mine").json(), room["id"]) is False


def test_mention_reading_the_room_clears_it(ws_client_factory):
    instance1 = ws_client_factory()
    instance2 = ws_client_factory()

    alice = _register_ws(instance1, _unique("alice"))
    room = instance1.post("/api/rooms", json={"name": _unique("general")}).json()

    bob = _register_ws(instance2, _unique("bob"))
    instance2.post(f"/api/rooms/{room['id']}/join")

    with instance1.websocket_connect("/ws/chat") as alice_ws:
        alice_ws.send_json({"type": "join", "room_id": room["id"]})
        assert alice_ws.receive_json()["type"] == "joined"
        message = _send_and_sync(alice_ws, room["id"], f"@{bob['username']} ping")
        assert message["type"] == "message"

    assert _has_mention(instance2.get("/api/rooms/mine").json(), room["id"]) is True

    resp = instance2.post(f"/api/rooms/{room['id']}/read")
    assert resp.status_code == 204

    assert _has_mention(instance2.get("/api/rooms/mine").json(), room["id"]) is False


def test_mention_customizes_push_body(ws_client_factory, monkeypatch):
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

    with instance1.websocket_connect("/ws/chat") as alice_ws:
        alice_ws.send_json({"type": "join", "room_id": room["id"]})
        assert alice_ws.receive_json()["type"] == "joined"
        message = _send_and_sync(alice_ws, room["id"], f"@{bob['username']} check this out")
        assert message["type"] == "message"

    assert len(calls) == 1
    assert "mentioned you" in calls[0]["data"]
    assert alice["username"] in calls[0]["data"]


def test_mention_requires_room_membership_to_count(ws_client_factory):
    # A username that exists on the site but isn't a member of *this* room
    # must not be resolvable as a mention here -- membership, not just
    # username existence, is what @username matches against.
    instance1 = ws_client_factory()
    instance2 = ws_client_factory()

    alice = _register_ws(instance1, _unique("alice"))
    room = instance1.post("/api/rooms", json={"name": _unique("general")}).json()

    outsider = _register_ws(instance2, _unique("outsider"))
    # Deliberately not joining `room`.

    with instance1.websocket_connect("/ws/chat") as alice_ws:
        alice_ws.send_json({"type": "join", "room_id": room["id"]})
        assert alice_ws.receive_json()["type"] == "joined"
        message = _send_and_sync(alice_ws, room["id"], f"@{outsider['username']} are you there?")
        assert message["type"] == "message"

    async def _mention_count() -> int:
        from sqlalchemy import select

        from app.models import MessageMention

        async with instance1.session_factory() as session:
            result = await session.execute(
                select(MessageMention).where(MessageMention.message_id == uuid.UUID(message["id"]))
            )
            return len(result.scalars().all())

    assert instance1.portal.call(_mention_count) == 0
