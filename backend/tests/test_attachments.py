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


def test_lists_files_and_images_actually_sent(ws_client):
    alice = _register_ws(ws_client, _unique("alice"))
    room = ws_client.post("/api/rooms", json={"name": _unique("general")}).json()

    file_upload = ws_client.post(
        f"/api/rooms/{room['id']}/files",
        files={"file": ("notes.txt", b"hello", "text/plain")},
    ).json()
    image_upload = ws_client.post(
        f"/api/rooms/{room['id']}/images",
        files={"file": ("pic.png", _png_bytes(), "image/png")},
    ).json()

    with ws_client.websocket_connect("/ws/chat") as ws:
        ws.send_json({"type": "join", "room_id": room["id"]})
        assert ws.receive_json()["type"] == "joined"

        ws.send_json({"type": "message", "room_id": room["id"], "file_id": file_upload["id"]})
        file_message = ws.receive_json()

        ws.send_json({"type": "message", "room_id": room["id"], "image_id": image_upload["id"]})
        image_message = ws.receive_json()

    resp = ws_client.get(f"/api/rooms/{room['id']}/attachments")
    assert resp.status_code == 200, resp.text
    attachments = resp.json()

    # Newest first.
    assert [a["kind"] for a in attachments] == ["image", "file"]

    image_entry, file_entry = attachments
    assert image_entry["id"] == image_upload["id"]
    assert image_entry["filename"] is None
    assert image_entry["content_type"] == "image/png"
    assert image_entry["uploaded_by"] == alice["username"]
    assert image_entry["message_id"] == image_message["id"]

    assert file_entry["id"] == file_upload["id"]
    assert file_entry["filename"] == "notes.txt"
    assert file_entry["content_type"] == "text/plain"
    assert file_entry["size_bytes"] == len(b"hello")
    assert file_entry["uploaded_by"] == alice["username"]
    assert file_entry["message_id"] == file_message["id"]


async def test_abandoned_upload_never_sent_is_excluded(client, db_session):
    # The scoping gotcha this feature exists to avoid: a file/image is
    # uploaded (and gets a DB row) before the message referencing it is
    # ever sent -- an upload nobody actually sent as a message must not
    # show up as a phantom attachment.
    await register_and_login(client, db_session, username=_unique("alice"))
    room = (await client.post("/api/rooms", json={"name": _unique("general")})).json()

    await client.post(
        f"/api/rooms/{room['id']}/files",
        files={"file": ("never-sent.txt", b"abandoned", "text/plain")},
    )

    resp = await client.get(f"/api/rooms/{room['id']}/attachments")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_attachments_require_room_membership(client, db_session):
    await register_and_login(client, db_session, username=_unique("alice"))
    room = (await client.post("/api/rooms", json={"name": _unique("general")})).json()

    await register_and_login(client, db_session, username=_unique("bob"))
    resp = await client.get(f"/api/rooms/{room['id']}/attachments")
    assert resp.status_code == 403


def test_attachments_scoped_to_room(ws_client):
    _register_ws(ws_client, _unique("alice"))
    room_a = ws_client.post("/api/rooms", json={"name": _unique("room-a")}).json()
    room_b = ws_client.post("/api/rooms", json={"name": _unique("room-b")}).json()

    upload = ws_client.post(
        f"/api/rooms/{room_a['id']}/files",
        files={"file": ("notes.txt", b"hello", "text/plain")},
    ).json()

    with ws_client.websocket_connect("/ws/chat") as ws:
        ws.send_json({"type": "join", "room_id": room_a["id"]})
        assert ws.receive_json()["type"] == "joined"
        ws.send_json({"type": "message", "room_id": room_a["id"], "file_id": upload["id"]})
        assert ws.receive_json()["type"] == "message"

    assert len(ws_client.get(f"/api/rooms/{room_a['id']}/attachments").json()) == 1
    assert ws_client.get(f"/api/rooms/{room_b['id']}/attachments").json() == []
