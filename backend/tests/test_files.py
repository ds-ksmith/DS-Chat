import uuid

from tests.conftest import register_and_login


def _unique(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


async def test_upload_file_succeeds(client, db_session):
    await register_and_login(client, db_session, username=_unique("alice"))
    room = (await client.post("/api/rooms", json={"name": _unique("general")})).json()

    resp = await client.post(
        f"/api/rooms/{room['id']}/files",
        files={"file": ("report.pdf", b"%PDF-1.4 not a real pdf", "application/pdf")},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert "id" in body
    assert body["filename"] == "report.pdf"
    assert body["size_bytes"] == len(b"%PDF-1.4 not a real pdf")
    assert body["content_type"] == "application/pdf"


async def test_upload_any_content_type_accepted(client, db_session):
    await register_and_login(client, db_session, username=_unique("alice"))
    room = (await client.post("/api/rooms", json={"name": _unique("general")})).json()

    # Unlike /images, /files has no content-type allowlist -- arbitrary
    # files are the point of this endpoint.
    resp = await client.post(
        f"/api/rooms/{room['id']}/files",
        files={"file": ("archive.zip", b"PK\x03\x04 not a real zip", "application/zip")},
    )
    assert resp.status_code == 201, resp.text


async def test_upload_oversized_file_rejected(client, db_session):
    await register_and_login(client, db_session, username=_unique("alice"))
    room = (await client.post("/api/rooms", json={"name": _unique("general")})).json()

    oversized = b"0" * (9 * 1024 * 1024)
    resp = await client.post(
        f"/api/rooms/{room['id']}/files",
        files={"file": ("huge.bin", oversized, "application/octet-stream")},
    )
    assert resp.status_code == 413


async def test_serve_file_requires_room_membership(client, db_session):
    await register_and_login(client, db_session, username=_unique("alice"))
    room = (await client.post("/api/rooms", json={"name": _unique("general")})).json()
    upload = await client.post(
        f"/api/rooms/{room['id']}/files",
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    file_id = upload.json()["id"]

    ok = await client.get(f"/api/rooms/{room['id']}/files/{file_id}")
    assert ok.status_code == 200

    await register_and_login(client, db_session, username=_unique("bob"))
    resp = await client.get(f"/api/rooms/{room['id']}/files/{file_id}")
    assert resp.status_code == 403


async def test_serve_file_404s_for_wrong_room(client, db_session):
    await register_and_login(client, db_session, username=_unique("alice"))
    room_a = (await client.post("/api/rooms", json={"name": _unique("room-a")})).json()
    room_b = (await client.post("/api/rooms", json={"name": _unique("room-b")})).json()
    upload = await client.post(
        f"/api/rooms/{room_a['id']}/files",
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    file_id = upload.json()["id"]

    resp = await client.get(f"/api/rooms/{room_b['id']}/files/{file_id}")
    assert resp.status_code == 404


async def test_serve_file_forces_download(client, db_session):
    # The security-relevant assertion for this feature: a user-uploaded
    # file must never render inline (e.g. an uploaded .html executing
    # script same-origin) -- Content-Disposition: attachment forces a
    # download in the browser regardless of content-type.
    await register_and_login(client, db_session, username=_unique("alice"))
    room = (await client.post("/api/rooms", json={"name": _unique("general")})).json()
    upload = await client.post(
        f"/api/rooms/{room['id']}/files",
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    file_id = upload.json()["id"]

    resp = await client.get(f"/api/rooms/{room['id']}/files/{file_id}")
    assert resp.status_code == 200
    disposition = resp.headers["content-disposition"]
    assert "attachment" in disposition
    assert "notes.txt" in disposition


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


def test_ws_file_only_message_roundtrips(ws_client):
    _register_ws(ws_client, _unique("alice"))
    room = ws_client.post("/api/rooms", json={"name": _unique("general")}).json()

    upload = ws_client.post(
        f"/api/rooms/{room['id']}/files",
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    file_id = upload.json()["id"]

    with ws_client.websocket_connect("/ws/chat") as ws:
        ws.send_json({"type": "join", "room_id": room["id"]})
        assert ws.receive_json()["type"] == "joined"

        ws.send_json({"type": "message", "room_id": room["id"], "file_id": file_id})
        message = ws.receive_json()
        assert message["type"] == "message"
        assert message["content"] is None
        assert message["file"]["id"] == file_id
        assert message["file"]["filename"] == "notes.txt"
        assert message["file"]["size_bytes"] == len(b"hello")

    history = ws_client.get(f"/api/rooms/{room['id']}/messages").json()
    persisted = next(m for m in history if m["id"] == message["id"])
    assert persisted["content"] is None
    assert persisted["file"]["id"] == file_id
    assert persisted["file"]["filename"] == "notes.txt"


def test_ws_message_requires_content_or_image_or_file(ws_client):
    _register_ws(ws_client, _unique("alice"))
    room = ws_client.post("/api/rooms", json={"name": _unique("general")}).json()

    with ws_client.websocket_connect("/ws/chat") as ws:
        ws.send_json({"type": "join", "room_id": room["id"]})
        assert ws.receive_json()["type"] == "joined"

        ws.send_json({"type": "message", "room_id": room["id"]})
        resp = ws.receive_json()
        assert resp["type"] == "error"


def test_push_body_says_sent_a_file_for_file_only_message(ws_client, monkeypatch):
    calls = []
    monkeypatch.setattr("app.services.push_service.webpush", lambda **kw: calls.append(kw))

    alice = _register_ws(ws_client, _unique("alice"))
    room = ws_client.post("/api/rooms", json={"name": _unique("general")}).json()

    _register_ws(ws_client, _unique("bob"))
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
        f"/api/rooms/{room['id']}/files",
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    file_id = upload.json()["id"]

    with ws_client.websocket_connect("/ws/chat") as ws:
        ws.send_json({"type": "join", "room_id": room["id"]})
        assert ws.receive_json()["type"] == "joined"
        ws.send_json({"type": "message", "room_id": room["id"], "file_id": file_id})
        assert ws.receive_json()["type"] == "message"
        ws.send_json({"type": "join", "room_id": room["id"]})
        assert ws.receive_json()["type"] == "joined"

    assert len(calls) == 1
    assert "sent a file" in calls[0]["data"]
