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

    # Monkeypatches get_smtp_settings directly rather than configuring it
    # for real through the admin endpoint (like test_smtp_settings.py's own
    # _configure_smtp does) -- ws_client_factory-based tests commit for
    # real, no rollback, and SmtpSettings is a genuine single global row.
    # Configuring it for real here previously leaked into every later test
    # in the same run, breaking test_smtp_settings.py's "starts
    # unconfigured" assumption. This never touches the DB at all.
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
    """Sync barrier -- see test_mentions.py's identical helper. The
    "message" ack fires the instant broadcaster.publish() runs, the very
    first line of broadcast_new_message -- it proves nothing about whether
    _maybe_email_dm_notification (awaited afterward, in the same handler)
    has finished. A second, idempotent join's own ack only arrives once
    the whole prior frame's handling -- including the email step -- is
    done, since one connection processes frames strictly sequentially."""
    ws.send_json({"type": "message", "room_id": room_id, "content": content})
    message = ws.receive_json()
    ws.send_json({"type": "join", "room_id": room_id})
    assert ws.receive_json()["type"] == "joined"
    return message


def test_dm_message_emails_globally_offline_recipient(ws_client_factory, monkeypatch):
    calls = _fake_smtp(monkeypatch)
    instance1 = ws_client_factory()
    instance2 = ws_client_factory()

    alice = _register_ws(instance1, _unique("alice"))
    bob = _register_ws(instance2, _unique("bob"))

    dm = instance1.post("/api/rooms/dm", json={"other_user_id": bob["id"]}).json()

    # bob never connects via WS at all -- genuinely offline, not just
    # absent from this room's own channel.
    with instance1.websocket_connect("/ws/chat") as alice_ws:
        alice_ws.send_json({"type": "join", "room_id": dm["id"]})
        assert alice_ws.receive_json()["type"] == "joined"
        _send_and_sync(alice_ws, dm["id"], "hey, you there?")

    assert len(calls) == 1
    email = calls[0]["message"]
    assert email["To"] == bob["email"]
    assert f"New message from {alice['username']}" in email["Subject"]
    body = email.get_content()
    assert f"{alice['username']}: hey, you there?" in body
    assert f"/rooms/{dm['id']}" in body


def test_dm_message_does_not_email_online_recipient(ws_client_factory, monkeypatch):
    calls = _fake_smtp(monkeypatch)
    instance1 = ws_client_factory()
    instance2 = ws_client_factory()

    alice = _register_ws(instance1, _unique("alice"))
    bob = _register_ws(instance2, _unique("bob"))

    dm = instance1.post("/api/rooms/dm", json={"other_user_id": bob["id"]}).json()

    with instance2.websocket_connect("/ws/chat"):
        # bob has an open connection -- genuinely online -- even though he
        # never joins the DM's own room channel.
        with instance1.websocket_connect("/ws/chat") as alice_ws:
            alice_ws.send_json({"type": "join", "room_id": dm["id"]})
            assert alice_ws.receive_json()["type"] == "joined"
            _send_and_sync(alice_ws, dm["id"], "hey")

    assert calls == []


def test_dm_message_emails_appear_offline_recipient_even_when_connected(ws_client_factory, monkeypatch):
    calls = _fake_smtp(monkeypatch)
    instance1 = ws_client_factory()
    instance2 = ws_client_factory()

    alice = _register_ws(instance1, _unique("alice"))
    bob = _register_ws(instance2, _unique("bob"))

    dm = instance1.post("/api/rooms/dm", json={"other_user_id": bob["id"]}).json()

    resp = instance2.patch("/api/auth/me", json={"appear_offline": True})
    assert resp.status_code == 200

    with instance2.websocket_connect("/ws/chat"):
        # bob is connected (genuinely online) but lurking -- appear_offline
        # should still count as "email me," matching how it already
        # overrides the presence dot everywhere else.
        with instance1.websocket_connect("/ws/chat") as alice_ws:
            alice_ws.send_json({"type": "join", "room_id": dm["id"]})
            assert alice_ws.receive_json()["type"] == "joined"
            _send_and_sync(alice_ws, dm["id"], "hey")

    assert len(calls) == 1
    assert calls[0]["message"]["To"] == bob["email"]


def test_regular_room_message_does_not_email_offline_member(ws_client_factory, monkeypatch):
    calls = _fake_smtp(monkeypatch)
    instance1 = ws_client_factory()
    instance2 = ws_client_factory()

    _register_ws(instance1, _unique("alice"))
    room = instance1.post("/api/rooms", json={"name": _unique("general")}).json()

    _register_ws(instance2, _unique("bob"))
    instance2.post(f"/api/rooms/{room['id']}/join")
    # bob never connects -- genuinely offline, same as the DM case -- but
    # this isn't a DM, so #66's email notification is out of scope here.

    with instance1.websocket_connect("/ws/chat") as alice_ws:
        alice_ws.send_json({"type": "join", "room_id": room["id"]})
        assert alice_ws.receive_json()["type"] == "joined"
        _send_and_sync(alice_ws, room["id"], "hello room")

    assert calls == []


def test_dm_email_debounced_to_first_unread_then_resets_after_read(ws_client_factory, monkeypatch):
    calls = _fake_smtp(monkeypatch)
    instance1 = ws_client_factory()
    instance2 = ws_client_factory()

    alice = _register_ws(instance1, _unique("alice"))
    bob = _register_ws(instance2, _unique("bob"))

    dm = instance1.post("/api/rooms/dm", json={"other_user_id": bob["id"]}).json()

    with instance1.websocket_connect("/ws/chat") as alice_ws:
        alice_ws.send_json({"type": "join", "room_id": dm["id"]})
        assert alice_ws.receive_json()["type"] == "joined"

        _send_and_sync(alice_ws, dm["id"], "message one")
        assert len(calls) == 1

        # A second message while bob still hasn't read the first -- no
        # second email for the same burst.
        _send_and_sync(alice_ws, dm["id"], "message two")
        assert len(calls) == 1

    # bob "reads" the conversation via REST -- he never has to have been
    # connected via WS for this to be meaningful, mark-read is independent
    # of live connection state.
    instance2.post(
        "/api/auth/login", json={"username_or_email": bob["username"], "password": "password123"}
    )
    read_resp = instance2.post(f"/api/rooms/{dm['id']}/read")
    assert read_resp.status_code == 204

    with instance1.websocket_connect("/ws/chat") as alice_ws:
        alice_ws.send_json({"type": "join", "room_id": dm["id"]})
        assert alice_ws.receive_json()["type"] == "joined"
        _send_and_sync(alice_ws, dm["id"], "message three")

    assert len(calls) == 2
