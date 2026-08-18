import uuid


def _unique(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _recv(ws) -> dict:
    """Reads the next frame, discarding member_updated presence-change
    broadcasts -- same convention as test_mentions.py/test_push.py."""
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


def _send_and_sync(ws, room_id: str, content: str) -> dict:
    """Sync barrier -- see test_mentions.py's identical helper. Proves the
    message frame's full handling (including the offline-notify step this
    feature hooks into) has completed before the test checks anything."""
    ws.send_json({"type": "message", "room_id": room_id, "content": content})
    message = ws.receive_json()
    ws.send_json({"type": "join", "room_id": room_id})
    assert ws.receive_json()["type"] == "joined"
    return message


def test_desktop_notification_delivered_to_offline_member(ws_client_factory):
    # #49: bob has an open connection (so he can receive his per-user
    # channel broadcast) but hasn't joined *this* room's channel -- exactly
    # the "app running, room not foregrounded" case _notify_offline_members
    # already treats as offline for push, and desktop notifications should
    # use the identical audience.
    instance1 = ws_client_factory()
    instance2 = ws_client_factory()

    alice = _register_ws(instance1, _unique("alice"))
    room = instance1.post("/api/rooms", json={"name": _unique("general")}).json()

    _register_ws(instance2, _unique("bob"))
    instance2.post(f"/api/rooms/{room['id']}/join")

    with instance2.websocket_connect("/ws/chat") as bob_ws:
        with instance1.websocket_connect("/ws/chat") as alice_ws:
            alice_ws.send_json({"type": "join", "room_id": room["id"]})
            assert alice_ws.receive_json()["type"] == "joined"
            message = _send_and_sync(alice_ws, room["id"], "hey, look at this")
            assert message["type"] == "message"

        # bob never joined the room's channel on his connection, so he's
        # "offline" for it even though instance2 is connected.
        bob_update = _recv(bob_ws)
        assert bob_update["type"] == "unread_update"

        desktop_note = _recv(bob_ws)
        assert desktop_note == {
            "type": "desktop_notification",
            "id": message["id"],
            "room_id": room["id"],
            "title": f"#{room['name']}",
            "body": f"{alice['username']}: hey, look at this",
        }


def test_desktop_notification_uses_mention_wording(ws_client_factory):
    instance1 = ws_client_factory()
    instance2 = ws_client_factory()

    alice = _register_ws(instance1, _unique("alice"))
    room = instance1.post("/api/rooms", json={"name": _unique("general")}).json()

    bob = _register_ws(instance2, _unique("bob"))
    instance2.post(f"/api/rooms/{room['id']}/join")

    with instance2.websocket_connect("/ws/chat") as bob_ws:
        with instance1.websocket_connect("/ws/chat") as alice_ws:
            alice_ws.send_json({"type": "join", "room_id": room["id"]})
            assert alice_ws.receive_json()["type"] == "joined"
            _send_and_sync(alice_ws, room["id"], f"@{bob['username']} check this out")

        _recv(bob_ws)  # unread_update
        desktop_note = _recv(bob_ws)
        assert desktop_note["type"] == "desktop_notification"
        assert desktop_note["body"] == f"{alice['username']} mentioned you: @{bob['username']} check this out"


def test_desktop_notification_not_sent_to_room_member_who_is_present(ws_client_factory):
    instance1 = ws_client_factory()
    instance2 = ws_client_factory()

    alice = _register_ws(instance1, _unique("alice"))
    room = instance1.post("/api/rooms", json={"name": _unique("general")}).json()

    _register_ws(instance2, _unique("bob"))
    instance2.post(f"/api/rooms/{room['id']}/join")

    with instance2.websocket_connect("/ws/chat") as bob_ws:
        bob_ws.send_json({"type": "join", "room_id": room["id"]})
        assert bob_ws.receive_json()["type"] == "joined"

        with instance1.websocket_connect("/ws/chat") as alice_ws:
            alice_ws.send_json({"type": "join", "room_id": room["id"]})
            assert alice_ws.receive_json()["type"] == "joined"
            _send_and_sync(alice_ws, room["id"], "hello")

        # bob is actively in the room -- he should only see the live
        # "message" broadcast, never an unread_update or desktop_notification.
        live_message = _recv(bob_ws)
        assert live_message["type"] == "message"


def test_desktop_notification_not_sent_to_non_member(ws_client_factory):
    instance1 = ws_client_factory()
    instance2 = ws_client_factory()

    _register_ws(instance1, _unique("alice"))
    room = instance1.post("/api/rooms", json={"name": _unique("general")}).json()

    _register_ws(instance2, _unique("outsider"))
    # Deliberately not joining `room`.

    with instance2.websocket_connect("/ws/chat") as outsider_ws:
        with instance1.websocket_connect("/ws/chat") as alice_ws:
            alice_ws.send_json({"type": "join", "room_id": room["id"]})
            assert alice_ws.receive_json()["type"] == "joined"
            _send_and_sync(alice_ws, room["id"], "hello")

        # Nothing should ever arrive on the outsider's own channel for a
        # room they aren't a member of. Send a harmless self-targeted
        # frame on a *different* room-less action and confirm the socket
        # stays quiet: simplest proof is a short, bounded wait via a
        # room creation (which touches no broadcast) -- if anything queued
        # up for outsider, it would already be sitting in the socket buffer.
        room2 = instance2.post("/api/rooms", json={"name": _unique("outsiders-room")}).json()
        outsider_ws.send_json({"type": "join", "room_id": room2["id"]})
        joined = outsider_ws.receive_json()
        assert joined == {"type": "joined", "room_id": room2["id"]}
