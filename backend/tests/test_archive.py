import uuid

from app.models import User
from app.schemas.user import UserCreate
from app.services.auth_service import register_user
from tests.conftest import register_and_login


def _unique(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


async def _make_admin(db_session, user_id: str) -> None:
    user = await db_session.get(User, uuid.UUID(user_id))
    user.is_site_admin = True
    await db_session.commit()


def _make_admin_ws(ws_client, user_id: str) -> None:
    async def _promote():
        async with ws_client.session_factory() as session:
            user = await session.get(User, uuid.UUID(user_id))
            user.is_site_admin = True
            await session.commit()

    ws_client.portal.call(_promote)


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


async def test_archived_room_flag_reaches_existing_members(client, db_session):
    # #57: is_archived used to only ever reach the admin portal's own
    # AdminRoom schema -- a member's own view of the room (GET /rooms/mine)
    # had no way to know it was archived at all.
    admin = await register_and_login(client, db_session, username=_unique("admin"))
    await _make_admin(db_session, admin["id"])
    room = (await client.post("/api/rooms", json={"name": _unique("general")})).json()

    resp = await client.post(f"/api/admin/rooms/{room['id']}/archive")
    assert resp.status_code == 200

    mine = (await client.get("/api/rooms/mine")).json()
    entry = next(r for r in mine if r["id"] == room["id"])
    assert entry["is_archived"] is True

    # History stays fully readable for an existing member.
    messages_resp = await client.get(f"/api/rooms/{room['id']}/messages")
    assert messages_resp.status_code == 200

    resp = await client.post(f"/api/admin/rooms/{room['id']}/unarchive")
    assert resp.status_code == 200
    mine = (await client.get("/api/rooms/mine")).json()
    entry = next(r for r in mine if r["id"] == room["id"])
    assert entry["is_archived"] is False


def test_ws_message_rejected_in_archived_room(ws_client_factory, db_session):
    admin_ws = ws_client_factory()
    admin = _register_ws(admin_ws, _unique("admin"))
    _make_admin_ws(admin_ws, admin["id"])
    room = admin_ws.post("/api/rooms", json={"name": _unique("general")}).json()

    archive_resp = admin_ws.post(f"/api/admin/rooms/{room['id']}/archive")
    assert archive_resp.status_code == 200

    with admin_ws.websocket_connect("/ws/chat") as ws:
        ws.send_json({"type": "join", "room_id": room["id"]})
        assert ws.receive_json()["type"] == "joined"

        ws.send_json({"type": "message", "room_id": room["id"], "content": "should not send"})
        received = ws.receive_json()
        assert received["type"] == "error"
        assert "archived" in received["detail"].lower()


def test_ws_message_allowed_again_after_unarchive(ws_client_factory):
    admin_ws = ws_client_factory()
    admin = _register_ws(admin_ws, _unique("admin"))
    _make_admin_ws(admin_ws, admin["id"])
    room = admin_ws.post("/api/rooms", json={"name": _unique("general")}).json()

    admin_ws.post(f"/api/admin/rooms/{room['id']}/archive")
    admin_ws.post(f"/api/admin/rooms/{room['id']}/unarchive")

    with admin_ws.websocket_connect("/ws/chat") as ws:
        ws.send_json({"type": "join", "room_id": room["id"]})
        assert ws.receive_json()["type"] == "joined"

        ws.send_json({"type": "message", "room_id": room["id"], "content": "back online"})
        received = ws.receive_json()
        assert received["type"] == "message"
        assert received["content"] == "back online"


async def test_incoming_webhook_rejected_in_archived_room(client, db_session):
    admin = await register_and_login(client, db_session, username=_unique("admin"))
    await _make_admin(db_session, admin["id"])
    room = (await client.post("/api/rooms", json={"name": _unique("general")})).json()
    webhook = (await client.post(f"/api/rooms/{room['id']}/webhooks/incoming", json={})).json()

    await client.post(f"/api/admin/rooms/{room['id']}/archive")

    resp = await client.post(
        f"/api/webhooks/incoming/{webhook['token']}", json={"content": "should not post"}
    )
    assert resp.status_code == 403
    assert "archived" in resp.json()["detail"].lower()
