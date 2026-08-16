import asyncio
import hashlib
import hmac
import json
import uuid

import pytest

from app.models import PushSubscription
from app.schemas.user import UserCreate
from app.services.auth_service import register_user
from app.services.room_service import join_room
from app.services.ssrf import UnsafeWebhookUrlError, validate_target_url
from tests.conftest import register_and_login


def test_validate_target_url_rejects_loopback():
    with pytest.raises(UnsafeWebhookUrlError):
        validate_target_url("http://127.0.0.1/hook")


def test_validate_target_url_rejects_private_range():
    with pytest.raises(UnsafeWebhookUrlError):
        validate_target_url("http://10.0.0.5/hook")


def test_validate_target_url_rejects_non_http_scheme():
    with pytest.raises(UnsafeWebhookUrlError):
        validate_target_url("ftp://8.8.8.8/hook")


def test_validate_target_url_accepts_public_address():
    # 8.8.8.8 is a stable, well-known public IP (Google's public DNS
    # resolver) -- a literal IP so this resolves without any real network
    # access (getaddrinfo parses a literal IP without touching DNS/the
    # network), and it isn't flagged by any of ipaddress's private/
    # reserved/loopback/etc checks, so it exercises the "allowed" path.
    # (203.0.113.0/24, the usual RFC 5737 documentation-only choice, is
    # actually flagged is_private by Python's ipaddress module -- not
    # usable here.)
    validate_target_url("http://8.8.8.8/hook")


async def test_event_subscription_rejects_private_target(client, db_session):
    await register_and_login(client, db_session, username="alice")
    room = (await client.post("/api/rooms", json={"name": "general"})).json()

    resp = await client.post(
        f"/api/rooms/{room['id']}/event-subscriptions",
        json={"event_types": ["message.created"], "target_url": "http://127.0.0.1/hook"},
    )
    assert resp.status_code == 400


async def test_incoming_webhook_unknown_token_404s(client, db_session):
    await register_and_login(client, db_session, username="alice")
    resp = await client.post("/api/webhooks/incoming/not-a-real-token", json={"content": "hi"})
    assert resp.status_code == 404


async def test_incoming_webhook_posts_message_and_pushes_offline_members(
    client, db_session, monkeypatch
):
    calls = []
    monkeypatch.setattr("app.services.push_service.webpush", lambda **kw: calls.append(kw))

    alice = await register_and_login(client, db_session, username="alice")
    room = (await client.post("/api/rooms", json={"name": "general"})).json()

    webhook_resp = await client.post(
        f"/api/rooms/{room['id']}/webhooks/incoming", json={"description": "CI bot"}
    )
    assert webhook_resp.status_code == 201
    webhook = webhook_resp.json()
    assert webhook["token"]

    bob = await register_user(
        db_session, UserCreate(username="bob", email="bob@example.com", password="password123")
    )
    await join_room(db_session, uuid.UUID(room["id"]), bob.id)
    db_session.add(
        PushSubscription(
            user_id=bob.id,
            endpoint="https://push.example.com/bob",
            p256dh_key="p256dh",
            auth_key="auth",
        )
    )
    await db_session.commit()

    post_resp = await client.post(
        f"/api/webhooks/incoming/{webhook['token']}", json={"content": "deploy succeeded"}
    )
    assert post_resp.status_code == 204

    history = (await client.get(f"/api/rooms/{room['id']}/messages")).json()
    assert any(m["content"] == "deploy succeeded" for m in history)

    # Exactly one push -- to bob. If the sender (webhook creator, alice) were
    # incorrectly included in "offline members" (no WS connection exists for
    # either party in this REST-only test), this would be 2.
    assert len(calls) == 1
    assert "deploy succeeded" in calls[0]["data"]


async def test_outgoing_webhook_delivers_signed_payload(client, db_session, monkeypatch):
    captured_tasks: list[asyncio.Task] = []
    real_create_task = asyncio.create_task

    def fake_create_task(coro):
        task = real_create_task(coro)
        captured_tasks.append(task)
        return task

    monkeypatch.setattr("app.services.webhook_service.asyncio.create_task", fake_create_task)

    posts = []

    class FakeResponse:
        status_code = 200

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, content=None, headers=None):
            posts.append({"url": url, "content": content, "headers": headers})
            return FakeResponse()

    monkeypatch.setattr("app.services.webhook_delivery.httpx.AsyncClient", FakeAsyncClient)

    await register_and_login(client, db_session, username="alice")
    room = (await client.post("/api/rooms", json={"name": "general"})).json()

    sub_resp = await client.post(
        f"/api/rooms/{room['id']}/event-subscriptions",
        json={"event_types": ["message.created"], "target_url": "http://8.8.8.8/hook"},
    )
    assert sub_resp.status_code == 201
    secret = sub_resp.json()["signing_secret"]

    webhook = (
        await client.post(f"/api/rooms/{room['id']}/webhooks/incoming", json={})
    ).json()
    resp = await client.post(
        f"/api/webhooks/incoming/{webhook['token']}", json={"content": "ping"}
    )
    assert resp.status_code == 204

    await asyncio.gather(*captured_tasks)

    assert len(posts) == 1
    body = posts[0]["content"]
    expected_signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    assert posts[0]["headers"]["X-DS-Chat-Signature"] == f"sha256={expected_signature}"
    payload = json.loads(body)
    assert payload["event"] == "message.created"
    assert payload["data"]["content"] == "ping"
