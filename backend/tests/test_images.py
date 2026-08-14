import io
import uuid

from PIL import Image

from tests.conftest import register_and_login


def _unique(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _png_bytes(size: tuple[int, int] = (10, 10)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color=(255, 0, 0)).save(buf, format="PNG")
    return buf.getvalue()


async def test_upload_image_succeeds(client, db_session):
    await register_and_login(client, db_session, username=_unique("alice"))
    room = (await client.post("/api/rooms", json={"name": _unique("general")})).json()

    resp = await client.post(
        f"/api/rooms/{room['id']}/images",
        files={"file": ("test.png", _png_bytes(), "image/png")},
    )
    assert resp.status_code == 201, resp.text
    assert "id" in resp.json()


async def test_upload_oversized_image_rejected(client, db_session):
    await register_and_login(client, db_session, username=_unique("alice"))
    room = (await client.post("/api/rooms", json={"name": _unique("general")})).json()

    # 8MB cap -- a bit over, so it's rejected promptly by the streamed byte
    # count in app/storage.read_capped without ever reaching Pillow.
    oversized = b"0" * (9 * 1024 * 1024)
    resp = await client.post(
        f"/api/rooms/{room['id']}/images",
        files={"file": ("huge.png", oversized, "image/png")},
    )
    assert resp.status_code == 413


async def test_upload_non_image_rejected(client, db_session):
    await register_and_login(client, db_session, username=_unique("alice"))
    room = (await client.post("/api/rooms", json={"name": _unique("general")})).json()

    # Spoofed Content-Type: claims image/png but isn't decodable as one --
    # must be caught by Pillow, not just the header check.
    resp = await client.post(
        f"/api/rooms/{room['id']}/images",
        files={"file": ("fake.png", b"not an image", "image/png")},
    )
    assert resp.status_code == 400


async def test_upload_unsupported_content_type_rejected(client, db_session):
    await register_and_login(client, db_session, username=_unique("alice"))
    room = (await client.post("/api/rooms", json={"name": _unique("general")})).json()

    resp = await client.post(
        f"/api/rooms/{room['id']}/images",
        files={"file": ("doc.pdf", b"%PDF-1.4", "application/pdf")},
    )
    assert resp.status_code == 400


async def test_serve_image_requires_room_membership(client, db_session):
    await register_and_login(client, db_session, username=_unique("alice"))
    room = (await client.post("/api/rooms", json={"name": _unique("general")})).json()
    upload = await client.post(
        f"/api/rooms/{room['id']}/images",
        files={"file": ("test.png", _png_bytes(), "image/png")},
    )
    image_id = upload.json()["id"]

    # Sanity: the uploader themselves can fetch it.
    ok = await client.get(f"/api/rooms/{room['id']}/images/{image_id}")
    assert ok.status_code == 200

    await register_and_login(client, db_session, username=_unique("bob"))
    resp = await client.get(f"/api/rooms/{room['id']}/images/{image_id}")
    assert resp.status_code == 403


async def test_serve_image_404s_for_wrong_room(client, db_session):
    await register_and_login(client, db_session, username=_unique("alice"))
    room_a = (await client.post("/api/rooms", json={"name": _unique("room-a")})).json()
    room_b = (await client.post("/api/rooms", json={"name": _unique("room-b")})).json()
    upload = await client.post(
        f"/api/rooms/{room_a['id']}/images",
        files={"file": ("test.png", _png_bytes(), "image/png")},
    )
    image_id = upload.json()["id"]

    resp = await client.get(f"/api/rooms/{room_b['id']}/images/{image_id}")
    assert resp.status_code == 404


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


def test_ws_image_only_message_roundtrips(ws_client):
    _register_ws(ws_client, _unique("alice"))
    room = ws_client.post("/api/rooms", json={"name": _unique("general")}).json()

    upload = ws_client.post(
        f"/api/rooms/{room['id']}/images",
        files={"file": ("test.png", _png_bytes(), "image/png")},
    )
    image_id = upload.json()["id"]

    with ws_client.websocket_connect("/ws/chat") as ws:
        ws.send_json({"type": "join", "room_id": room["id"]})
        assert ws.receive_json()["type"] == "joined"

        ws.send_json({"type": "message", "room_id": room["id"], "image_id": image_id})
        message = ws.receive_json()
        assert message["type"] == "message"
        assert message["content"] is None
        assert message["image_id"] == image_id

    history = ws_client.get(f"/api/rooms/{room['id']}/messages").json()
    persisted = next(m for m in history if m["id"] == message["id"])
    assert persisted["content"] is None
    assert persisted["image_id"] == image_id


def test_ws_message_requires_content_or_image(ws_client):
    _register_ws(ws_client, _unique("alice"))
    room = ws_client.post("/api/rooms", json={"name": _unique("general")}).json()

    with ws_client.websocket_connect("/ws/chat") as ws:
        ws.send_json({"type": "join", "room_id": room["id"]})
        assert ws.receive_json()["type"] == "joined"

        ws.send_json({"type": "message", "room_id": room["id"]})
        resp = ws.receive_json()
        assert resp["type"] == "error"


def test_push_body_says_sent_an_image_for_image_only_message(ws_client, monkeypatch):
    calls = []
    monkeypatch.setattr("app.services.push_service.webpush", lambda **kw: calls.append(kw))

    alice = _register_ws(ws_client, _unique("alice"))
    room = ws_client.post("/api/rooms", json={"name": _unique("general")}).json()

    bob = _register_ws(ws_client, _unique("bob"))
    ws_client.post(f"/api/rooms/{room['id']}/join")
    ws_client.post(
        "/api/push/subscribe",
        json={
            "endpoint": f"https://push.example.com/ep-{_unique('bob')}",
            "keys": {"p256dh": "p256dh-bob", "auth": "auth-bob"},
        },
    )

    ws_client.post(
        "/api/auth/login", json={"username_or_email": alice["username"], "password": "password123"}
    )
    upload = ws_client.post(
        f"/api/rooms/{room['id']}/images",
        files={"file": ("test.png", _png_bytes(), "image/png")},
    )
    image_id = upload.json()["id"]

    with ws_client.websocket_connect("/ws/chat") as ws:
        ws.send_json({"type": "join", "room_id": room["id"]})
        assert ws.receive_json()["type"] == "joined"
        ws.send_json({"type": "message", "room_id": room["id"], "image_id": image_id})
        assert ws.receive_json()["type"] == "message"
        # Sync barrier -- see test_push.py's identical pattern for why this
        # is needed before checking server-side push side effects.
        ws.send_json({"type": "join", "room_id": room["id"]})
        assert ws.receive_json()["type"] == "joined"

    assert len(calls) == 1
    assert "sent an image" in calls[0]["data"]
