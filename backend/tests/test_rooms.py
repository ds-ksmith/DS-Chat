import io
import uuid

from PIL import Image
from sqlalchemy import select

from app.models import (
    EventSubscription,
    MessageFile,
    MessageImage,
    MessageRoomReference,
    Room,
    RoomMembership,
    RoomRole,
    User,
    WebhookIncoming,
)
from app.schemas.user import UserCreate
from app.services.auth_service import register_user
from app.storage import UPLOADS_DIR
from tests.conftest import login_as, register_and_login


def _unique(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _png_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (10, 10), color=(255, 0, 0)).save(buf, format="PNG")
    return buf.getvalue()


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


async def test_create_room_requires_auth(client):
    resp = await client.post("/api/rooms", json={"name": "general"})
    assert resp.status_code == 401


async def test_create_room_creates_owner_membership(client, db_session):
    user = await register_and_login(client, db_session, username="alice")
    resp = await client.post("/api/rooms", json={"name": "general", "description": "chat"})
    assert resp.status_code == 201
    room = resp.json()
    assert room["name"] == "general"
    assert room["owner_id"] == user["id"]

    result = await db_session.execute(
        select(RoomMembership).where(RoomMembership.room_id == uuid.UUID(room["id"]))
    )
    membership = result.scalar_one()
    assert membership.user_id == uuid.UUID(user["id"])
    assert membership.role == RoomRole.owner


async def test_my_rooms_tiebreaks_identical_created_at_by_id(client, db_session):
    # Two rooms sharing the exact same created_at (bulk-created/migrated
    # rooms, or just an unlucky timing collision) must still come back in a
    # single, stable order every call -- see list_member_rooms's order_by
    # comment. Without a secondary sort key, a second fetch (e.g. from a
    # different device) isn't guaranteed to return ties in the same order.
    await register_and_login(client, db_session, username="alice")
    room_a = (await client.post("/api/rooms", json={"name": "room-a"})).json()
    room_b = (await client.post("/api/rooms", json={"name": "room-b"})).json()

    result = await db_session.execute(
        select(Room).where(Room.id.in_([uuid.UUID(room_a["id"]), uuid.UUID(room_b["id"])]))
    )
    rooms_by_id = {str(r.id): r for r in result.scalars().all()}
    rooms_by_id[room_a["id"]].created_at = rooms_by_id[room_b["id"]].created_at
    await db_session.commit()

    resp = await client.get("/api/rooms/mine")
    assert resp.status_code == 200
    ids = [r["id"] for r in resp.json() if r["id"] in (room_a["id"], room_b["id"])]
    assert ids == sorted([room_a["id"], room_b["id"]])


async def test_list_rooms_excludes_private(client, db_session):
    user = await register_and_login(client, db_session, username="alice")
    await client.post("/api/rooms", json={"name": "open-room"})

    private_room = Room(
        name="secret-room", is_private=True, owner_id=uuid.UUID(user["id"])
    )
    db_session.add(private_room)
    await db_session.commit()

    resp = await client.get("/api/rooms")
    assert resp.status_code == 200
    names = {r["name"] for r in resp.json()}
    assert "open-room" in names
    assert "secret-room" not in names


async def test_join_room_idempotent(client, db_session):
    await register_and_login(client, db_session, username="alice")
    create_resp = await client.post("/api/rooms", json={"name": "general"})
    room_id = create_resp.json()["id"]

    await client.post("/api/auth/logout")
    await register_and_login(client, db_session, username="bob")

    resp1 = await client.post(f"/api/rooms/{room_id}/join")
    assert resp1.status_code == 200
    resp2 = await client.post(f"/api/rooms/{room_id}/join")
    assert resp2.status_code == 200


async def test_join_nonexistent_room_404(client, db_session):
    await register_and_login(client, db_session, username="alice")
    resp = await client.post(f"/api/rooms/{uuid.uuid4()}/join")
    assert resp.status_code == 404


async def test_join_private_room_400(client, db_session):
    user = await register_and_login(client, db_session, username="alice")
    private_room = Room(
        name="secret-room", is_private=True, owner_id=uuid.UUID(user["id"])
    )
    db_session.add(private_room)
    await db_session.commit()
    await db_session.refresh(private_room)

    resp = await client.post(f"/api/rooms/{private_room.id}/join")
    assert resp.status_code == 400


async def test_create_private_room_excluded_from_open_list_but_in_mine(client, db_session):
    await register_and_login(client, db_session, username="alice")
    resp = await client.post("/api/rooms", json={"name": "secret", "is_private": True})
    assert resp.status_code == 201
    assert resp.json()["is_private"] is True

    open_names = {r["name"] for r in (await client.get("/api/rooms")).json()}
    assert "secret" not in open_names

    mine = (await client.get("/api/rooms/mine")).json()
    assert mine[0]["name"] == "secret"
    assert mine[0]["role"] == "owner"


async def test_update_room_requires_admin(client, db_session):
    await register_and_login(client, db_session, username="alice")
    room_id = (await client.post("/api/rooms", json={"name": "general"})).json()["id"]

    await client.post("/api/auth/logout")
    await register_and_login(client, db_session, username="bob")
    await client.post(f"/api/rooms/{room_id}/join")

    resp = await client.patch(f"/api/rooms/{room_id}", json={"description": "nope"})
    assert resp.status_code == 403

    await client.post("/api/auth/logout")
    await login_as(client, "alice")
    resp = await client.patch(f"/api/rooms/{room_id}", json={"description": "updated"})
    assert resp.status_code == 200
    assert resp.json()["description"] == "updated"


async def test_update_room_is_private_toggles_open_room_visibility(client, db_session):
    # #48: owner can flip an already-created room's privacy after the fact.
    await register_and_login(client, db_session, username="alice")
    room_id = (await client.post("/api/rooms", json={"name": "general"})).json()["id"]
    assert "general" in {r["name"] for r in (await client.get("/api/rooms")).json()}

    resp = await client.patch(f"/api/rooms/{room_id}", json={"is_private": True})
    assert resp.status_code == 200
    assert resp.json()["is_private"] is True
    assert "general" not in {r["name"] for r in (await client.get("/api/rooms")).json()}

    resp = await client.patch(f"/api/rooms/{room_id}", json={"is_private": False})
    assert resp.status_code == 200
    assert resp.json()["is_private"] is False
    assert "general" in {r["name"] for r in (await client.get("/api/rooms")).json()}


async def test_update_room_is_private_allowed_for_room_admin_not_just_owner(client, db_session):
    alice = await register_and_login(client, db_session, username="alice")
    room_id = (await client.post("/api/rooms", json={"name": "general"})).json()["id"]

    await client.post("/api/auth/logout")
    bob = await register_and_login(client, db_session, username="bob")
    await client.post(f"/api/rooms/{room_id}/join")

    await client.post("/api/auth/logout")
    await login_as(client, "alice")
    resp = await client.patch(
        f"/api/rooms/{room_id}/members/{bob['id']}", json={"role": "admin"}
    )
    assert resp.status_code == 200

    await client.post("/api/auth/logout")
    await login_as(client, "bob")
    resp = await client.patch(f"/api/rooms/{room_id}", json={"is_private": True})
    assert resp.status_code == 200
    assert resp.json()["is_private"] is True


async def test_update_room_is_private_allowed_for_site_admin_non_member(client, db_session):
    await register_and_login(client, db_session, username="alice")
    room_id = (await client.post("/api/rooms", json={"name": "general"})).json()["id"]

    await client.post("/api/auth/logout")
    admin = await register_and_login(client, db_session, username="carol")
    user = await db_session.get(User, uuid.UUID(admin["id"]))
    user.is_site_admin = True
    await db_session.commit()

    # Never joined "general" -- ordinarily require_room_role would 403 this
    # as "Not a member of this room" before even checking role.
    resp = await client.patch(f"/api/rooms/{room_id}", json={"is_private": True})
    assert resp.status_code == 200
    assert resp.json()["is_private"] is True


async def test_delete_room_owner_only(client, db_session):
    await register_and_login(client, db_session, username="alice")
    room_id = (await client.post("/api/rooms", json={"name": "general"})).json()["id"]

    await client.post("/api/auth/logout")
    await register_and_login(client, db_session, username="bob")
    await client.post(f"/api/rooms/{room_id}/join")

    resp = await client.delete(f"/api/rooms/{room_id}")
    assert resp.status_code == 403

    await client.post("/api/auth/logout")
    await login_as(client, "alice")
    resp = await client.delete(f"/api/rooms/{room_id}")
    assert resp.status_code == 204

    result = await db_session.execute(
        select(RoomMembership).where(RoomMembership.room_id == uuid.UUID(room_id))
    )
    assert result.scalar_one_or_none() is None


def test_delete_room_with_attachments_integrations_and_cross_room_reference(ws_client):
    # Reproduces #55: every table below has a room_id (or message_id, for a
    # room being deleted) foreign key with no ON DELETE CASCADE at the DB
    # level, so a room that's ever had an attachment, an integration, or
    # been #referenced from another room's message used to 500 on delete.
    # This sets up one of each and confirms delete_room cleans all of them
    # up, not just whichever one originally surfaced the bug.
    _register_ws(ws_client, _unique("alice"))
    target_name = _unique("target-room")
    other_name = _unique("other-room")
    target = ws_client.post("/api/rooms", json={"name": target_name}).json()
    other = ws_client.post("/api/rooms", json={"name": other_name}).json()

    image_id = ws_client.post(
        f"/api/rooms/{target['id']}/images",
        files={"file": ("test.png", _png_bytes(), "image/png")},
    ).json()["id"]
    file_upload = ws_client.post(
        f"/api/rooms/{target['id']}/files",
        files={"file": ("report.pdf", b"%PDF-1.4 not real", "application/pdf")},
    ).json()
    file_id = file_upload["id"]

    webhook = ws_client.post(f"/api/rooms/{target['id']}/webhooks/incoming", json={}).json()
    sub = ws_client.post(
        f"/api/rooms/{target['id']}/event-subscriptions",
        json={"event_types": ["message.created"], "target_url": "http://8.8.8.8/hook"},
    ).json()

    with ws_client.websocket_connect("/ws/chat") as ws:
        ws.send_json({"type": "join", "room_id": target["id"]})
        assert ws.receive_json()["type"] == "joined"
        ws.send_json({"type": "message", "room_id": target["id"], "image_id": image_id})
        ws.receive_json()
        ws.send_json({"type": "message", "room_id": target["id"], "file_id": file_id})
        ws.receive_json()

        ws.send_json({"type": "join", "room_id": other["id"]})
        assert ws.receive_json()["type"] == "joined"
        # References target-room from a message that belongs to a
        # *different* room -- the direction that originally 500'd, since
        # it's keyed by the referenced room's id, not the message's room.
        ws.send_json({"type": "message", "room_id": other["id"], "content": f"check out #{target_name}"})
        other_message = ws.receive_json()

    async def _storage_filenames():
        async with ws_client.session_factory() as session:
            image = await session.get(MessageImage, uuid.UUID(image_id))
            file = await session.get(MessageFile, uuid.UUID(file_id))
            return image.storage_filename, file.storage_filename

    image_filename, file_filename = ws_client.portal.call(_storage_filenames)
    assert (UPLOADS_DIR / image_filename).exists()
    assert (UPLOADS_DIR / file_filename).exists()

    resp = ws_client.delete(f"/api/rooms/{target['id']}")
    assert resp.status_code == 204, resp.text

    async def _assert_cleaned_up():
        async with ws_client.session_factory() as session:
            target_id = uuid.UUID(target["id"])
            for model in (MessageImage, MessageFile, WebhookIncoming, EventSubscription):
                result = await session.execute(select(model).where(model.room_id == target_id))
                assert result.scalar_one_or_none() is None, model.__name__
            result = await session.execute(
                select(MessageRoomReference).where(MessageRoomReference.room_id == target_id)
            )
            assert result.scalar_one_or_none() is None

    ws_client.portal.call(_assert_cleaned_up)

    # The physical files were unlinked too, not just the DB rows.
    assert not (UPLOADS_DIR / image_filename).exists()
    assert not (UPLOADS_DIR / file_filename).exists()

    # Sanity: deleting target-room didn't touch the unrelated other-room or
    # its message -- the cross-room reference cleanup is scoped correctly.
    history = ws_client.get(f"/api/rooms/{other['id']}/messages").json()
    assert any(m["id"] == other_message["id"] for m in history)
    assert webhook["id"] and sub["id"]  # created successfully, not otherwise asserted above


async def test_leave_room(client, db_session):
    await register_and_login(client, db_session, username="alice")
    room_id = (await client.post("/api/rooms", json={"name": "general"})).json()["id"]

    resp = await client.post(f"/api/rooms/{room_id}/leave")
    assert resp.status_code == 400  # owner must transfer first

    await client.post("/api/auth/logout")
    await register_and_login(client, db_session, username="bob")
    await client.post(f"/api/rooms/{room_id}/join")
    resp = await client.post(f"/api/rooms/{room_id}/leave")
    assert resp.status_code == 204

    resp = await client.get(f"/api/rooms/{room_id}/messages")
    assert resp.status_code == 403  # no longer a member


async def test_remove_member(client, db_session):
    await register_and_login(client, db_session, username="alice")
    room_id = (await client.post("/api/rooms", json={"name": "general"})).json()["id"]

    await client.post("/api/auth/logout")
    bob = await register_and_login(client, db_session, username="bob")
    await client.post(f"/api/rooms/{room_id}/join")

    await client.post("/api/auth/logout")
    await login_as(client, "alice")
    resp = await client.delete(f"/api/rooms/{room_id}/members/{bob['id']}")
    assert resp.status_code == 204

    resp = await client.delete(f"/api/rooms/{room_id}/members/{bob['id']}")
    assert resp.status_code == 404


async def test_admin_cannot_remove_another_admin(client, db_session):
    await register_and_login(client, db_session, username="alice")
    room_id = (await client.post("/api/rooms", json={"name": "general"})).json()["id"]

    await client.post("/api/auth/logout")
    bob = await register_and_login(client, db_session, username="bob")
    await client.post(f"/api/rooms/{room_id}/join")

    await client.post("/api/auth/logout")
    carol = await register_and_login(client, db_session, username="carol")
    await client.post(f"/api/rooms/{room_id}/join")

    await client.post("/api/auth/logout")
    await login_as(client, "alice")
    resp = await client.patch(f"/api/rooms/{room_id}/members/{bob['id']}", json={"role": "admin"})
    assert resp.status_code == 200
    assert resp.json()["role"] == "admin"
    resp = await client.patch(f"/api/rooms/{room_id}/members/{carol['id']}", json={"role": "admin"})
    assert resp.status_code == 200

    await client.post("/api/auth/logout")
    await login_as(client, "bob")
    resp = await client.delete(f"/api/rooms/{room_id}/members/{carol['id']}")
    assert resp.status_code == 403


async def test_cannot_remove_owner(client, db_session):
    await register_and_login(client, db_session, username="alice")
    room_id = (await client.post("/api/rooms", json={"name": "general"})).json()["id"]

    await client.post("/api/auth/logout")
    bob = await register_and_login(client, db_session, username="bob")
    await client.post(f"/api/rooms/{room_id}/join")

    await client.post("/api/auth/logout")
    await login_as(client, "alice")
    await client.patch(f"/api/rooms/{room_id}/members/{bob['id']}", json={"role": "admin"})

    resp = await client.delete(f"/api/rooms/{room_id}/members/{(await client.get('/api/auth/me')).json()['id']}")
    assert resp.status_code == 400


async def test_transfer_ownership(client, db_session):
    await register_and_login(client, db_session, username="alice")
    room_id = (await client.post("/api/rooms", json={"name": "general"})).json()["id"]

    await client.post("/api/auth/logout")
    bob = await register_and_login(client, db_session, username="bob")
    await client.post(f"/api/rooms/{room_id}/join")

    await client.post("/api/auth/logout")
    await login_as(client, "alice")
    resp = await client.post(
        f"/api/rooms/{room_id}/transfer-ownership", json={"new_owner_user_id": bob["id"]}
    )
    assert resp.status_code == 200
    assert resp.json()["owner_id"] == bob["id"]

    resp = await client.post(f"/api/rooms/{room_id}/leave")
    assert resp.status_code == 204  # alice is admin now, not owner, so she can leave

    result = await db_session.execute(
        select(RoomMembership).where(
            RoomMembership.room_id == uuid.UUID(room_id), RoomMembership.user_id == uuid.UUID(bob["id"])
        )
    )
    assert result.scalar_one().role == RoomRole.owner


async def test_change_member_role_owner_only(client, db_session):
    await register_and_login(client, db_session, username="alice")
    room_id = (await client.post("/api/rooms", json={"name": "general"})).json()["id"]

    await client.post("/api/auth/logout")
    bob = await register_and_login(client, db_session, username="bob")
    await client.post(f"/api/rooms/{room_id}/join")
    resp = await client.patch(f"/api/rooms/{room_id}/members/{bob['id']}", json={"role": "admin"})
    assert resp.status_code == 403  # bob is a plain member, not owner


def _fake_send_email(monkeypatch):
    calls = []

    async def fake(db, to, subject, paragraphs, **kwargs):
        calls.append({"to": to, "subject": subject, "paragraphs": paragraphs, **kwargs})

    monkeypatch.setattr("app.services.room_service.send_email", fake)
    return calls


async def test_add_member_directly(client, db_session, monkeypatch):
    calls = _fake_send_email(monkeypatch)
    await register_and_login(client, db_session, username="alice")
    room_id = (await client.post("/api/rooms", json={"name": "general"})).json()["id"]

    await client.post("/api/auth/logout")
    bob = await register_and_login(client, db_session, username="bob")

    await client.post("/api/auth/logout")
    await login_as(client, "alice")
    resp = await client.post(f"/api/rooms/{room_id}/members", json={"user_id": bob["id"]})
    assert resp.status_code == 201, resp.text
    assert resp.json()["username"] == "bob"
    assert resp.json()["role"] == "member"

    result = await db_session.execute(
        select(RoomMembership).where(
            RoomMembership.room_id == uuid.UUID(room_id), RoomMembership.user_id == uuid.UUID(bob["id"])
        )
    )
    assert result.scalar_one().role == RoomRole.member

    assert len(calls) == 1
    assert calls[0]["to"] == bob["email"]
    assert "added" in calls[0]["subject"].lower()


async def test_add_member_requires_admin_role(client, db_session, monkeypatch):
    _fake_send_email(monkeypatch)
    await register_and_login(client, db_session, username="alice")
    room_id = (await client.post("/api/rooms", json={"name": "general"})).json()["id"]

    await client.post("/api/auth/logout")
    bob = await register_and_login(client, db_session, username="bob")
    await client.post(f"/api/rooms/{room_id}/join")

    carol = await register_and_login(client, db_session, username="carol")

    resp = await client.post(f"/api/rooms/{room_id}/members", json={"user_id": carol["id"]})
    assert resp.status_code == 403


async def test_add_member_already_member_conflict(client, db_session, monkeypatch):
    _fake_send_email(monkeypatch)
    await register_and_login(client, db_session, username="alice")
    room_id = (await client.post("/api/rooms", json={"name": "general"})).json()["id"]

    await client.post("/api/auth/logout")
    bob = await register_and_login(client, db_session, username="bob")
    await client.post(f"/api/rooms/{room_id}/join")

    await client.post("/api/auth/logout")
    await login_as(client, "alice")
    resp = await client.post(f"/api/rooms/{room_id}/members", json={"user_id": bob["id"]})
    assert resp.status_code == 409


async def test_add_member_unknown_user_404(client, db_session, monkeypatch):
    _fake_send_email(monkeypatch)
    await register_and_login(client, db_session, username="alice")
    room_id = (await client.post("/api/rooms", json={"name": "general"})).json()["id"]

    resp = await client.post(f"/api/rooms/{room_id}/members", json={"user_id": str(uuid.uuid4())})
    assert resp.status_code == 404


async def test_list_room_members(client, db_session):
    await register_and_login(client, db_session, username="alice")
    room_id = (await client.post("/api/rooms", json={"name": "general"})).json()["id"]

    resp = await client.get(f"/api/rooms/{room_id}/members")
    assert resp.status_code == 200
    members = resp.json()
    assert len(members) == 1
    assert members[0]["username"] == "alice"
    assert members[0]["role"] == "owner"
