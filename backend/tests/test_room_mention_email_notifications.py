import uuid

from app.models import SmtpSettings
from app.schemas.user import UserCreate
from app.services.auth_service import register_user


def _unique(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _fake_smtp(monkeypatch):
    calls = []

    async def fake_send(message, **kwargs):
        calls.append({"message": message, **kwargs})

    monkeypatch.setattr("app.services.email_service.aiosmtplib.send", fake_send)

    # See test_dm_email_notifications.py's identical helper for why this
    # monkeypatches get_smtp_settings directly instead of configuring a real
    # row through the admin endpoint.
    fake_settings = SmtpSettings(
        host="smtp.example.com",
        port=587,
        username="bot",
        password_encrypted=None,
        from_address="noreply@example.com",
        use_tls=True,
    )

    async def fake_get_smtp_settings(db):
        return fake_settings

    monkeypatch.setattr("app.services.email_service.get_smtp_settings", fake_get_smtp_settings)
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


def _send_and_sync(ws, room_id: str, content: str) -> dict:
    """See test_dm_email_notifications.py's identical helper -- the
    "message" ack alone proves nothing about whether the email step
    (awaited afterward in the same handler) has finished; a second,
    idempotent join's ack only arrives once the whole frame is done."""
    ws.send_json({"type": "message", "room_id": room_id, "content": content})
    message = ws.receive_json()
    ws.send_json({"type": "join", "room_id": room_id})
    assert ws.receive_json()["type"] == "joined"
    return message


def _subscribe(ws_client, room_id: str, username: str, password: str = "password123") -> None:
    login = ws_client.post(
        "/api/auth/login", json={"username_or_email": username, "password": password}
    )
    assert login.status_code == 200, login.text
    resp = ws_client.patch(f"/api/rooms/{room_id}/notifications", json={"email_notifications": True})
    assert resp.status_code == 204, resp.text


def test_room_first_message_emails_offline_subscribed_member(ws_client_factory, monkeypatch):
    calls = _fake_smtp(monkeypatch)
    instance1 = ws_client_factory()
    instance2 = ws_client_factory()

    alice = _register_ws(instance1, _unique("alice"))
    bob = _register_ws(instance2, _unique("bob"))
    room = instance1.post("/api/rooms", json={"name": _unique("general")}).json()
    instance2.post(f"/api/rooms/{room['id']}/join")
    _subscribe(instance2, room["id"], bob["username"])
    # bob never connects via WS -- genuinely offline.

    with instance1.websocket_connect("/ws/chat") as alice_ws:
        alice_ws.send_json({"type": "join", "room_id": room["id"]})
        assert alice_ws.receive_json()["type"] == "joined"
        _send_and_sync(alice_ws, room["id"], "no mention here, just a plain message")

    assert len(calls) == 1
    email = calls[0]["message"]
    assert email["To"] == bob["email"]
    assert f"New message in #{room['name']}" in email["Subject"]
    body = email.get_body(preferencelist=("plain",)).get_content()
    assert alice["username"] in body
    assert f"/rooms/{room['id']}" in body


def test_room_second_plain_message_does_not_reemail_before_read(ws_client_factory, monkeypatch):
    calls = _fake_smtp(monkeypatch)
    instance1 = ws_client_factory()
    instance2 = ws_client_factory()

    _register_ws(instance1, _unique("alice"))
    bob = _register_ws(instance2, _unique("bob"))
    room = instance1.post("/api/rooms", json={"name": _unique("general")}).json()
    instance2.post(f"/api/rooms/{room['id']}/join")
    _subscribe(instance2, room["id"], bob["username"])

    with instance1.websocket_connect("/ws/chat") as alice_ws:
        alice_ws.send_json({"type": "join", "room_id": room["id"]})
        assert alice_ws.receive_json()["type"] == "joined"

        _send_and_sync(alice_ws, room["id"], "message one")
        assert len(calls) == 1

        # A second plain message while bob still hasn't read the first --
        # no second email for the same unread burst.
        _send_and_sync(alice_ws, room["id"], "message two")
        assert len(calls) == 1


def test_room_mention_always_emails_even_mid_unread_burst(ws_client_factory, monkeypatch):
    calls = _fake_smtp(monkeypatch)
    instance1 = ws_client_factory()
    instance2 = ws_client_factory()

    alice = _register_ws(instance1, _unique("alice"))
    bob = _register_ws(instance2, _unique("bob"))
    room = instance1.post("/api/rooms", json={"name": _unique("general")}).json()
    instance2.post(f"/api/rooms/{room['id']}/join")
    _subscribe(instance2, room["id"], bob["username"])

    with instance1.websocket_connect("/ws/chat") as alice_ws:
        alice_ws.send_json({"type": "join", "room_id": room["id"]})
        assert alice_ws.receive_json()["type"] == "joined"

        # First unread message (plain) -- emails once, uses up the debounce.
        _send_and_sync(alice_ws, room["id"], "hey everyone")
        assert len(calls) == 1

        # A mention arriving while that first message is still unread --
        # must email anyway, unlike a second plain message.
        _send_and_sync(alice_ws, room["id"], f"@{bob['username']} specifically you")
        assert len(calls) == 2

    mention_email = calls[1]["message"]
    assert mention_email["To"] == bob["email"]
    assert f"New mention in #{room['name']}" in mention_email["Subject"]
    body = mention_email.get_body(preferencelist=("plain",)).get_content()
    assert f"{alice['username']} mentioned you" in body


def test_room_mention_does_not_email_unsubscribed_member(ws_client_factory, monkeypatch):
    calls = _fake_smtp(monkeypatch)
    instance1 = ws_client_factory()
    instance2 = ws_client_factory()

    _register_ws(instance1, _unique("alice"))
    bob = _register_ws(instance2, _unique("bob"))
    room = instance1.post("/api/rooms", json={"name": _unique("general")}).json()
    instance2.post(f"/api/rooms/{room['id']}/join")
    # bob never opts in -- email_notifications defaults to False.

    with instance1.websocket_connect("/ws/chat") as alice_ws:
        alice_ws.send_json({"type": "join", "room_id": room["id"]})
        assert alice_ws.receive_json()["type"] == "joined"
        _send_and_sync(alice_ws, room["id"], f"hey @{bob['username']}")

    assert calls == []


def test_room_message_does_not_email_online_subscribed_member(ws_client_factory, monkeypatch):
    calls = _fake_smtp(monkeypatch)
    instance1 = ws_client_factory()
    instance2 = ws_client_factory()

    _register_ws(instance1, _unique("alice"))
    bob = _register_ws(instance2, _unique("bob"))
    room = instance1.post("/api/rooms", json={"name": _unique("general")}).json()
    instance2.post(f"/api/rooms/{room['id']}/join")
    _subscribe(instance2, room["id"], bob["username"])

    with instance2.websocket_connect("/ws/chat"):
        # bob has an open connection -- genuinely online -- even though he
        # never joins this room's own channel.
        with instance1.websocket_connect("/ws/chat") as alice_ws:
            alice_ws.send_json({"type": "join", "room_id": room["id"]})
            assert alice_ws.receive_json()["type"] == "joined"
            _send_and_sync(alice_ws, room["id"], f"hey @{bob['username']}")

    assert calls == []


def test_room_notifications_reset_after_read(ws_client_factory, monkeypatch):
    calls = _fake_smtp(monkeypatch)
    instance1 = ws_client_factory()
    instance2 = ws_client_factory()

    _register_ws(instance1, _unique("alice"))
    bob = _register_ws(instance2, _unique("bob"))
    room = instance1.post("/api/rooms", json={"name": _unique("general")}).json()
    instance2.post(f"/api/rooms/{room['id']}/join")
    _subscribe(instance2, room["id"], bob["username"])

    with instance1.websocket_connect("/ws/chat") as alice_ws:
        alice_ws.send_json({"type": "join", "room_id": room["id"]})
        assert alice_ws.receive_json()["type"] == "joined"
        _send_and_sync(alice_ws, room["id"], "message one")
        assert len(calls) == 1

    instance2.post(
        "/api/auth/login", json={"username_or_email": bob["username"], "password": "password123"}
    )
    read_resp = instance2.post(f"/api/rooms/{room['id']}/read")
    assert read_resp.status_code == 204

    with instance1.websocket_connect("/ws/chat") as alice_ws:
        alice_ws.send_json({"type": "join", "room_id": room["id"]})
        assert alice_ws.receive_json()["type"] == "joined"
        _send_and_sync(alice_ws, room["id"], "message two")

    assert len(calls) == 2


def test_enabling_notifications_rejected_for_dm(ws_client_factory):
    instance1 = ws_client_factory()
    instance2 = ws_client_factory()

    _register_ws(instance1, _unique("alice"))
    bob = _register_ws(instance2, _unique("bob"))
    dm = instance1.post("/api/rooms/dm", json={"other_user_id": bob["id"]}).json()

    resp = instance1.patch(f"/api/rooms/{dm['id']}/notifications", json={"email_notifications": True})
    assert resp.status_code == 400


def test_notifications_setting_reflected_in_my_rooms(ws_client_factory):
    instance1 = ws_client_factory()
    _register_ws(instance1, _unique("alice"))
    room = instance1.post("/api/rooms", json={"name": _unique("general")}).json()

    rooms = instance1.get("/api/rooms/mine").json()
    mine = next(r for r in rooms if r["id"] == room["id"])
    assert mine["email_notifications"] is False

    resp = instance1.patch(f"/api/rooms/{room['id']}/notifications", json={"email_notifications": True})
    assert resp.status_code == 204

    rooms = instance1.get("/api/rooms/mine").json()
    mine = next(r for r in rooms if r["id"] == room["id"])
    assert mine["email_notifications"] is True
