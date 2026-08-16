import uuid

from pywebpush import WebPushException
from sqlalchemy import select

from app.models import PushSubscription
from tests.conftest import login_as, register_and_login


def _subscription_payload(suffix: str = "a") -> dict:
    return {
        "endpoint": f"https://push.example.com/ep-{suffix}",
        "keys": {"p256dh": f"p256dh-{suffix}", "auth": f"auth-{suffix}"},
    }


async def test_vapid_public_key_endpoint(client, db_session):
    await register_and_login(client, db_session, username="alice")
    resp = await client.get("/api/push/vapid-public-key")
    assert resp.status_code == 200
    assert "public_key" in resp.json()


def _unique_suffix() -> str:
    return uuid.uuid4().hex[:8]


async def test_subscribe_creates_row(client, db_session):
    await register_and_login(client, db_session, username="alice")
    payload = _subscription_payload(_unique_suffix())
    resp = await client.post("/api/push/subscribe", json=payload)
    assert resp.status_code == 204

    # The ds_chat_test database is shared across the whole suite and the
    # ws_client-based tests below intentionally don't roll back (see
    # conftest.ws_client), so a unique endpoint keeps this test independent
    # of leftover rows from those instead of asserting on the total count.
    result = await db_session.execute(
        select(PushSubscription).where(PushSubscription.endpoint == payload["endpoint"])
    )
    rows = result.scalars().all()
    assert len(rows) == 1


async def test_subscribe_upserts_by_endpoint(client, db_session):
    await register_and_login(client, db_session, username="alice")
    payload = _subscription_payload(_unique_suffix())
    assert (await client.post("/api/push/subscribe", json=payload)).status_code == 204

    updated = {**payload, "keys": {"p256dh": "new-p256dh", "auth": "new-auth"}}
    assert (await client.post("/api/push/subscribe", json=updated)).status_code == 204

    result = await db_session.execute(
        select(PushSubscription).where(PushSubscription.endpoint == payload["endpoint"])
    )
    rows = result.scalars().all()
    assert len(rows) == 1
    assert rows[0].p256dh_key == "new-p256dh"


async def test_unsubscribe_removes_row(client, db_session):
    await register_and_login(client, db_session, username="alice")
    payload = _subscription_payload(_unique_suffix())
    await client.post("/api/push/subscribe", json=payload)

    resp = await client.request(
        "DELETE", "/api/push/subscribe", json={"endpoint": payload["endpoint"]}
    )
    assert resp.status_code == 204

    result = await db_session.execute(
        select(PushSubscription).where(PushSubscription.endpoint == payload["endpoint"])
    )
    assert result.scalars().all() == []


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


def _unique(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _fetch_subscriptions(ws_client, user_id: str) -> list[PushSubscription]:
    async def _query():
        async with ws_client.session_factory() as session:
            result = await session.execute(
                select(PushSubscription).where(PushSubscription.user_id == uuid.UUID(user_id))
            )
            return list(result.scalars().all())

    return ws_client.portal.call(_query)


def test_ws_message_pushes_offline_member_only(ws_client, monkeypatch):
    calls = []

    def fake_webpush(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr("app.services.push_service.webpush", fake_webpush)

    alice = _register_ws(ws_client, _unique("alice"))
    room = ws_client.post("/api/rooms", json={"name": _unique("general")}).json()

    bob = _register_ws(ws_client, _unique("bob"))
    ws_client.post(f"/api/rooms/{room['id']}/join")
    ws_client.post("/api/push/subscribe", json=_subscription_payload(_unique("bob")))

    login_resp = ws_client.post(
        "/api/auth/login", json={"username_or_email": alice["username"], "password": "password123"}
    )
    assert login_resp.status_code == 200

    with ws_client.websocket_connect("/ws/chat") as ws:
        ws.send_json({"type": "join", "room_id": room["id"]})
        assert ws.receive_json()["type"] == "joined"
        ws.send_json({"type": "message", "room_id": room["id"], "content": "hello"})
        assert ws.receive_json()["type"] == "message"
        # The handler processes frames strictly sequentially, so a second
        # (idempotent) join only gets acked once the "message" frame's full
        # handling -- including the offline-push step -- has completed. A
        # plain `with` block exit doesn't guarantee that: closing can race
        # ahead of (and cancel) still-in-flight server-side work.
        ws.send_json({"type": "join", "room_id": room["id"]})
        assert ws.receive_json()["type"] == "joined"

    assert len(calls) == 1
    assert calls[0]["subscription_info"]["endpoint"].startswith("https://push.example.com/ep-bob")
    assert "hello" in calls[0]["data"]
    assert alice["username"] in calls[0]["data"]  # sender attribution in the payload


def test_ws_message_no_push_when_member_connected(ws_client, monkeypatch):
    calls = []
    monkeypatch.setattr("app.services.push_service.webpush", lambda **kw: calls.append(kw))

    alice = _register_ws(ws_client, _unique("alice"))
    room = ws_client.post("/api/rooms", json={"name": _unique("general")}).json()

    bob = _register_ws(ws_client, _unique("bob"))
    ws_client.post(f"/api/rooms/{room['id']}/join")
    ws_client.post("/api/push/subscribe", json=_subscription_payload(_unique("bob")))

    with ws_client.websocket_connect("/ws/chat") as bob_ws:
        bob_ws.send_json({"type": "join", "room_id": room["id"]})
        assert bob_ws.receive_json()["type"] == "joined"

        ws_client.post(
            "/api/auth/login",
            json={"username_or_email": alice["username"], "password": "password123"},
        )
        with ws_client.websocket_connect("/ws/chat") as alice_ws:
            alice_ws.send_json({"type": "join", "room_id": room["id"]})
            assert alice_ws.receive_json()["type"] == "joined"
            alice_ws.send_json({"type": "message", "room_id": room["id"], "content": "hi"})
            assert alice_ws.receive_json()["type"] == "message"
            # bob is connected too -- he should get the broadcast, not a push
            assert bob_ws.receive_json()["type"] == "message"

    assert calls == []


def test_expired_subscription_is_cleaned_up(ws_client, monkeypatch):
    class FakeResponse:
        status_code = 410

    def fake_webpush(**kwargs):
        raise WebPushException("gone", response=FakeResponse())

    monkeypatch.setattr("app.services.push_service.webpush", fake_webpush)

    alice = _register_ws(ws_client, _unique("alice"))
    room = ws_client.post("/api/rooms", json={"name": _unique("general")}).json()

    bob = _register_ws(ws_client, _unique("bob"))
    ws_client.post(f"/api/rooms/{room['id']}/join")
    ws_client.post("/api/push/subscribe", json=_subscription_payload(_unique("bob")))
    assert len(_fetch_subscriptions(ws_client, bob["id"])) == 1

    ws_client.post(
        "/api/auth/login", json={"username_or_email": alice["username"], "password": "password123"}
    )
    with ws_client.websocket_connect("/ws/chat") as ws:
        ws.send_json({"type": "join", "room_id": room["id"]})
        assert ws.receive_json()["type"] == "joined"
        ws.send_json({"type": "message", "room_id": room["id"], "content": "hello"})
        assert ws.receive_json()["type"] == "message"
        # See test_ws_message_pushes_offline_member_only for why this sync
        # barrier is needed before checking server-side push side effects.
        ws.send_json({"type": "join", "room_id": room["id"]})
        assert ws.receive_json()["type"] == "joined"

    assert _fetch_subscriptions(ws_client, bob["id"]) == []
