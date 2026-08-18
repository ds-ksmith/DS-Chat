import asyncio
import uuid

import pytest_asyncio

from app.database import engine as _link_preview_engine
from app.schemas.user import UserCreate
from app.services.auth_service import register_user
from app.services.link_preview_service import extract_first_url
from tests.conftest import register_and_login


@pytest_asyncio.fixture(autouse=True)
async def _dispose_engine_between_tests():
    # link_preview_service's background task uses app.database's module-
    # level engine directly (see test_cli.py's identical fixture for why:
    # pytest-asyncio's per-test event loops make a stale pooled connection
    # from an earlier test's loop fail with asyncpg "another operation is
    # in progress" -- silently, in this file's case, since
    # fetch_and_broadcast_link_preview catches and logs rather than raises).
    yield
    await _link_preview_engine.dispose()


def _unique(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _unique_url() -> str:
    # link_previews rows are written via the background task's own,
    # separately-committed DB session (see link_preview_service.py), not
    # the db_session fixture's rollback-at-teardown transaction -- they're
    # real, permanent rows that persist across test runs. A literal URL
    # shared between tests (or repeated suite runs) would silently hit an
    # earlier run's cached row instead of exercising a fresh fetch.
    return f"http://8.8.8.8/{uuid.uuid4().hex}"


def _recv(ws) -> dict:
    """Reads the next frame, discarding member_updated presence-change
    broadcasts -- same convention as test_message_edit.py."""
    while True:
        msg = ws.receive_json()
        if msg.get("type") != "member_updated":
            return msg


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


class _FakeResponse:
    def __init__(self, status_code=200, headers=None, body=b""):
        self.status_code = status_code
        self.headers = headers or {}
        self.is_redirect = status_code in (301, 302, 303, 307, 308)
        self._body = body

    async def aiter_bytes(self):
        yield self._body


class _FakeStreamCtx:
    def __init__(self, response):
        self._response = response

    async def __aenter__(self):
        return self._response

    async def __aexit__(self, *args):
        return False


_OG_HTML = (
    b"<html><head>"
    b'<meta property="og:title" content="Example Article">'
    b'<meta property="og:description" content="A description of the article.">'
    b'<meta property="og:image" content="https://8.8.8.8/image.png">'
    b'<meta property="og:site_name" content="Example">'
    b"</head></html>"
)


def _fake_client_factory(html=_OG_HTML, status_code=200, call_log=None, content_type="text/html"):
    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        def stream(self, method, url, headers=None):
            if call_log is not None:
                call_log.append(url)
            return _FakeStreamCtx(_FakeResponse(status_code, {"content-type": content_type}, html))

    return _FakeAsyncClient


def test_extract_first_url_finds_url_in_content():
    assert extract_first_url("check out https://example.com for more") == "https://example.com"


def test_extract_first_url_strips_trailing_punctuation():
    assert extract_first_url("see (https://example.com/page).") == "https://example.com/page"


def test_extract_first_url_returns_none_without_url():
    assert extract_first_url("no links here") is None


def test_extract_first_url_returns_none_for_empty_content():
    assert extract_first_url(None) is None
    assert extract_first_url("") is None


def test_ws_message_with_url_triggers_link_preview_broadcast(ws_client, monkeypatch):
    monkeypatch.setattr("app.services.link_preview_service.httpx.AsyncClient", _fake_client_factory())
    url = _unique_url()

    username = _unique("alice")
    _register_ws(ws_client, username=username)
    room = ws_client.post("/api/rooms", json={"name": _unique("general")}).json()

    with ws_client.websocket_connect("/ws/chat") as ws:
        ws.send_json({"type": "join", "room_id": room["id"]})
        assert _recv(ws)["type"] == "joined"

        ws.send_json({"type": "message", "room_id": room["id"], "content": f"check this out {url}"})
        message = _recv(ws)
        assert message["type"] == "message"
        # Never populated on the initial broadcast -- fetching is async.
        assert message["link_preview"] is None

        preview = _recv(ws)
        assert preview["type"] == "link_preview"
        assert preview["id"] == message["id"]
        assert preview["url"] == url
        assert preview["title"] == "Example Article"
        assert preview["description"] == "A description of the article."
        assert preview["image_url"] == "https://8.8.8.8/image.png"
        assert preview["site_name"] == "Example"
        assert preview["is_image"] is False


def test_ws_message_with_direct_image_url_expands_the_image(ws_client, monkeypatch):
    monkeypatch.setattr(
        "app.services.link_preview_service.httpx.AsyncClient",
        _fake_client_factory(html=b"", content_type="image/png"),
    )
    url = _unique_url() + ".png"

    username = _unique("alice")
    _register_ws(ws_client, username=username)
    room = ws_client.post("/api/rooms", json={"name": _unique("general")}).json()

    with ws_client.websocket_connect("/ws/chat") as ws:
        ws.send_json({"type": "join", "room_id": room["id"]})
        assert _recv(ws)["type"] == "joined"

        ws.send_json({"type": "message", "room_id": room["id"], "content": f"lol {url}"})
        message = _recv(ws)
        assert message["link_preview"] is None

        preview = _recv(ws)
        assert preview["type"] == "link_preview"
        assert preview["url"] == url
        assert preview["image_url"] == url
        assert preview["is_image"] is True
        assert preview["title"] is None
        assert preview["description"] is None
        assert preview["site_name"] is None


def test_ws_message_with_private_url_gets_no_preview(ws_client, monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(
        "app.services.link_preview_service.httpx.AsyncClient",
        _fake_client_factory(call_log=calls),
    )

    username = _unique("alice")
    _register_ws(ws_client, username=username)
    room = ws_client.post("/api/rooms", json={"name": _unique("general")}).json()

    with ws_client.websocket_connect("/ws/chat") as ws:
        ws.send_json({"type": "join", "room_id": room["id"]})
        assert _recv(ws)["type"] == "joined"

        ws.send_json(
            {
                "type": "message",
                "room_id": room["id"],
                "content": "internal link http://127.0.0.1/secret",
            }
        )
        message = _recv(ws)
        assert message["link_preview"] is None

        # Sync barrier: an idempotent second frame's ack proves the first
        # message's entire async handling (including the spawned link-
        # preview task, which is rejected before any real I/O) has settled
        # without ever publishing a link_preview envelope.
        ws.send_json({"type": "join", "room_id": room["id"]})
        assert _recv(ws)["type"] == "joined"

    assert calls == []


async def test_message_history_includes_cached_link_preview(client, db_session, monkeypatch):
    captured_tasks: list[asyncio.Task] = []
    real_create_task = asyncio.create_task

    def fake_create_task(coro):
        task = real_create_task(coro)
        captured_tasks.append(task)
        return task

    monkeypatch.setattr("app.services.message_events.asyncio.create_task", fake_create_task)
    monkeypatch.setattr("app.services.link_preview_service.httpx.AsyncClient", _fake_client_factory())
    url = _unique_url()

    await register_and_login(client, db_session, username="alice")
    room = (await client.post("/api/rooms", json={"name": "general"})).json()
    webhook = (await client.post(f"/api/rooms/{room['id']}/webhooks/incoming", json={})).json()

    resp = await client.post(
        f"/api/webhooks/incoming/{webhook['token']}",
        json={"content": f"see {url}"},
    )
    assert resp.status_code == 204
    await asyncio.gather(*captured_tasks)

    history = (await client.get(f"/api/rooms/{room['id']}/messages")).json()
    assert len(history) == 1
    assert history[0]["link_preview"]["title"] == "Example Article"
    assert history[0]["link_preview"]["url"] == url


async def test_link_preview_reused_across_messages_with_same_url(client, db_session, monkeypatch):
    captured_tasks: list[asyncio.Task] = []
    real_create_task = asyncio.create_task

    def fake_create_task(coro):
        task = real_create_task(coro)
        captured_tasks.append(task)
        return task

    monkeypatch.setattr("app.services.message_events.asyncio.create_task", fake_create_task)
    calls: list[str] = []
    monkeypatch.setattr(
        "app.services.link_preview_service.httpx.AsyncClient",
        _fake_client_factory(call_log=calls),
    )
    url = _unique_url()

    await register_and_login(client, db_session, username="alice")
    room = (await client.post("/api/rooms", json={"name": "general"})).json()
    webhook = (await client.post(f"/api/rooms/{room['id']}/webhooks/incoming", json={})).json()

    # Awaited one at a time so the second send's cache check happens after
    # the first's fetch has actually committed -- otherwise both could race
    # past the "not cached yet" check concurrently and this would flake.
    resp1 = await client.post(
        f"/api/webhooks/incoming/{webhook['token']}", json={"content": f"see {url}"}
    )
    assert resp1.status_code == 204
    await asyncio.gather(*captured_tasks)
    captured_tasks.clear()

    resp2 = await client.post(
        f"/api/webhooks/incoming/{webhook['token']}", json={"content": f"again: {url}"}
    )
    assert resp2.status_code == 204
    await asyncio.gather(*captured_tasks)

    assert len(calls) == 1

    history = (await client.get(f"/api/rooms/{room['id']}/messages")).json()
    assert len(history) == 2
    assert all(m["link_preview"]["title"] == "Example Article" for m in history)
