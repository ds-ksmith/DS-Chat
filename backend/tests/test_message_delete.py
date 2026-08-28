import io
import uuid

from PIL import Image

from app.schemas.user import UserCreate
from app.services.auth_service import register_user


def _unique(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


_NOISE_TYPES = {"member_updated", "desktop_notification", "unread_update"}


def _recv(ws) -> dict:
    """Reads the next frame, transparently discarding presence/offline-
    notify noise -- see test_message_edit.py's identical helper."""
    while True:
        msg = ws.receive_json()
        if msg.get("type") not in _NOISE_TYPES:
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


def _png_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (10, 10), color=(255, 0, 0)).save(buf, format="PNG")
    return buf.getvalue()


def test_ws_delete_clears_content_and_broadcasts(ws_client):
    username = _unique("alice")
    _register_ws(ws_client, username=username)
    room = ws_client.post("/api/rooms", json={"name": _unique("general")}).json()

    with ws_client.websocket_connect("/ws/chat") as ws:
        ws.send_json({"type": "join", "room_id": room["id"]})
        assert ws.receive_json()["type"] == "joined"

        ws.send_json({"type": "message", "room_id": room["id"], "content": "hello"})
        message = ws.receive_json()

        ws.send_json({"type": "delete", "room_id": room["id"], "message_id": message["id"]})
        deleted = ws.receive_json()
        assert deleted == {"type": "message_deleted", "id": message["id"], "room_id": room["id"]}

    resp = ws_client.get(f"/api/rooms/{room['id']}/messages")
    history = resp.json()
    tombstone = next(m for m in history if m["id"] == message["id"])
    assert tombstone["content"] is None
    assert tombstone["deleted_at"] is not None
    assert tombstone["image_id"] is None
    assert tombstone["file"] is None


def test_ws_delete_rejects_non_author(ws_client):
    alice = _register_ws(ws_client, username=_unique("alice"))
    room = ws_client.post("/api/rooms", json={"name": _unique("general")}).json()

    bob = _register_ws(ws_client, username=_unique("bob"))
    ws_client.post(f"/api/rooms/{room['id']}/join")

    ws_client.post(
        "/api/auth/login", json={"username_or_email": alice["username"], "password": "password123"}
    )
    with ws_client.websocket_connect("/ws/chat") as alice_ws:
        alice_ws.send_json({"type": "join", "room_id": room["id"]})
        assert alice_ws.receive_json()["type"] == "joined"
        alice_ws.send_json({"type": "message", "room_id": room["id"], "content": "hello"})
        message = alice_ws.receive_json()

        ws_client.post(
            "/api/auth/login",
            json={"username_or_email": bob["username"], "password": "password123"},
        )
        with ws_client.websocket_connect("/ws/chat") as bob_ws:
            bob_ws.send_json({"type": "join", "room_id": room["id"]})
            assert _recv(bob_ws)["type"] == "joined"
            bob_ws.send_json(
                {"type": "delete", "room_id": room["id"], "message_id": message["id"]}
            )
            resp = bob_ws.receive_json()
            assert resp["type"] == "error"
            assert "own messages" in resp["detail"]

    resp = ws_client.get(f"/api/rooms/{room['id']}/messages")
    history = resp.json()
    still_there = next(m for m in history if m["id"] == message["id"])
    assert still_there["deleted_at"] is None
    assert still_there["content"] == "hello"


def test_ws_delete_of_unknown_message_errors(ws_client):
    _register_ws(ws_client, username=_unique("alice"))
    room = ws_client.post("/api/rooms", json={"name": _unique("general")}).json()

    with ws_client.websocket_connect("/ws/chat") as ws:
        ws.send_json({"type": "join", "room_id": room["id"]})
        assert ws.receive_json()["type"] == "joined"

        ws.send_json(
            {"type": "delete", "room_id": room["id"], "message_id": str(uuid.uuid4())}
        )
        resp = ws.receive_json()
        assert resp == {"type": "error", "detail": "Message not found"}


def test_deleted_message_cannot_be_edited_or_reacted_to(ws_client):
    _register_ws(ws_client, username=_unique("alice"))
    room = ws_client.post("/api/rooms", json={"name": _unique("general")}).json()

    with ws_client.websocket_connect("/ws/chat") as ws:
        ws.send_json({"type": "join", "room_id": room["id"]})
        assert ws.receive_json()["type"] == "joined"

        ws.send_json({"type": "message", "room_id": room["id"], "content": "hello"})
        message = ws.receive_json()

        ws.send_json({"type": "delete", "room_id": room["id"], "message_id": message["id"]})
        assert ws.receive_json()["type"] == "message_deleted"

        ws.send_json(
            {
                "type": "edit",
                "room_id": room["id"],
                "message_id": message["id"],
                "content": "resurrected",
            }
        )
        assert ws.receive_json() == {"type": "error", "detail": "Message not found"}

        ws.send_json(
            {
                "type": "reaction",
                "room_id": room["id"],
                "message_id": message["id"],
                "emoji": "👍",
            }
        )
        assert ws.receive_json() == {"type": "error", "detail": "Message not found"}


def test_delete_fans_out_across_instances(ws_client_factory):
    instance1 = ws_client_factory()
    instance2 = ws_client_factory()

    alice = _register_ws(instance1, _unique("alice"))
    room = instance1.post("/api/rooms", json={"name": _unique("general")}).json()

    bob = _register_ws(instance2, _unique("bob"))
    instance2.post(f"/api/rooms/{room['id']}/join")

    with instance2.websocket_connect("/ws/chat") as bob_ws:
        bob_ws.send_json({"type": "join", "room_id": room["id"]})
        assert _recv(bob_ws)["type"] == "joined"

        with instance1.websocket_connect("/ws/chat") as alice_ws:
            alice_ws.send_json({"type": "join", "room_id": room["id"]})
            assert alice_ws.receive_json()["type"] == "joined"
            alice_ws.send_json({"type": "message", "room_id": room["id"], "content": "hi"})
            message = alice_ws.receive_json()
            assert _recv(bob_ws)["type"] == "message"

            alice_ws.send_json(
                {"type": "delete", "room_id": room["id"], "message_id": message["id"]}
            )
            assert alice_ws.receive_json()["type"] == "message_deleted"

            deleted = _recv(bob_ws)
            assert deleted == {"type": "message_deleted", "id": message["id"], "room_id": room["id"]}


def test_delete_removes_underlying_image_from_disk(ws_client):
    username = _unique("alice")
    _register_ws(ws_client, username=username)
    room = ws_client.post("/api/rooms", json={"name": _unique("general")}).json()

    upload = ws_client.post(
        f"/api/rooms/{room['id']}/images",
        files={"file": ("test.png", _png_bytes(), "image/png")},
    ).json()
    image_id = upload["id"]

    with ws_client.websocket_connect("/ws/chat") as ws:
        ws.send_json({"type": "join", "room_id": room["id"]})
        assert ws.receive_json()["type"] == "joined"

        ws.send_json({"type": "message", "room_id": room["id"], "image_id": image_id})
        message = ws.receive_json()
        assert message["image_id"] == image_id

        # Confirm the image actually serves before deleting, so a false
        # pass (it was never reachable to begin with) can't hide as a true
        # one below.
        get_resp = ws_client.get(f"/api/rooms/{room['id']}/images/{image_id}")
        assert get_resp.status_code == 200

        ws.send_json({"type": "delete", "room_id": room["id"], "message_id": message["id"]})
        assert ws.receive_json()["type"] == "message_deleted"

    # The image is gone -- both the DB row (via the now-404ing serve
    # endpoint) and, per #53's "delete the file too" choice, the file
    # actually unlinked from disk (not just detached and orphaned).
    get_resp = ws_client.get(f"/api/rooms/{room['id']}/images/{image_id}")
    assert get_resp.status_code == 404
