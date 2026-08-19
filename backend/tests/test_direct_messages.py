import uuid

from sqlalchemy import select

from app.models import Room, RoomMembership
from app.schemas.user import UserCreate
from app.services.auth_service import register_user
from app.services.room_service import dm_room_name
from tests.conftest import login_as, register_and_login


def _unique(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


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


async def test_start_dm_creates_private_room_with_both_members(client, db_session):
    alice = await register_and_login(client, db_session, username="alice")
    await client.post("/api/auth/logout")
    bob = await register_and_login(client, db_session, username="bob")
    await client.post("/api/auth/logout")
    await login_as(client, "alice")

    resp = await client.post("/api/rooms/dm", json={"other_user_id": bob["id"]})
    assert resp.status_code == 201, resp.text
    room = resp.json()
    assert room["is_dm"] is True
    assert room["is_private"] is True
    # The internal name is never meant to be shown, but its scheme is part
    # of the contract find_or_create_dm relies on -- pin it here so a
    # future refactor can't silently change it without this test noticing.
    assert room["name"] == dm_room_name(uuid.UUID(alice["id"]), uuid.UUID(bob["id"]))

    result = await db_session.execute(
        select(RoomMembership.user_id).where(RoomMembership.room_id == uuid.UUID(room["id"]))
    )
    member_ids = {str(row[0]) for row in result.all()}
    assert member_ids == {alice["id"], bob["id"]}


async def test_start_dm_is_idempotent_regardless_of_who_initiates(client, db_session):
    alice = await register_and_login(client, db_session, username="alice")
    await client.post("/api/auth/logout")
    bob = await register_and_login(client, db_session, username="bob")

    resp1 = await client.post("/api/rooms/dm", json={"other_user_id": alice["id"]})
    assert resp1.status_code == 201
    room_id = resp1.json()["id"]

    # bob -> alice again should return the same room, not create a second one.
    resp2 = await client.post("/api/rooms/dm", json={"other_user_id": alice["id"]})
    assert resp2.status_code == 201
    assert resp2.json()["id"] == room_id

    await client.post("/api/auth/logout")
    await login_as(client, "alice")
    # alice -> bob (reversed direction) should also find the same room.
    resp3 = await client.post("/api/rooms/dm", json={"other_user_id": bob["id"]})
    assert resp3.status_code == 201
    assert resp3.json()["id"] == room_id


async def test_start_dm_rejects_self(client, db_session):
    alice = await register_and_login(client, db_session, username="alice")
    resp = await client.post("/api/rooms/dm", json={"other_user_id": alice["id"]})
    assert resp.status_code == 400


async def test_start_dm_404s_for_unknown_user(client, db_session):
    await register_and_login(client, db_session, username="alice")
    resp = await client.post("/api/rooms/dm", json={"other_user_id": str(uuid.uuid4())})
    assert resp.status_code == 404


async def test_dm_excluded_from_browse_rooms(client, db_session):
    alice = await register_and_login(client, db_session, username="alice")
    await client.post("/api/auth/logout")
    bob = await register_and_login(client, db_session, username="bob")
    await client.post("/api/rooms/dm", json={"other_user_id": alice["id"]})

    # A third user should never see the DM in the open-rooms listing, even
    # though find_or_create_dm sets is_private=True (which alone would
    # already exclude it) -- confirms the belt-and-suspenders is_dm filter
    # in list_open_rooms is doing something, not just is_private.
    await client.post("/api/auth/logout")
    await register_and_login(client, db_session, username="carol")
    resp = await client.get("/api/rooms")
    assert resp.status_code == 200
    assert all(not r["is_dm"] for r in resp.json())


async def test_dm_excluded_from_admin_room_list(client, db_session):
    alice = await register_and_login(client, db_session, username="alice")
    await client.post("/api/auth/logout")
    bob = await register_and_login(client, db_session, username="bob")
    await client.post("/api/rooms/dm", json={"other_user_id": alice["id"]})

    await client.post("/api/auth/logout")
    admin = await register_and_login(client, db_session, username="dave")
    from app.models import User

    user = await db_session.get(User, uuid.UUID(admin["id"]))
    user.is_site_admin = True
    await db_session.commit()

    resp = await client.get("/api/admin/rooms")
    assert resp.status_code == 200
    names = [r["name"] for r in resp.json()]
    assert dm_room_name(uuid.UUID(alice["id"]), uuid.UUID(bob["id"])) not in names


async def test_dm_appears_in_mine_with_partner_info(client, db_session):
    alice = await register_and_login(client, db_session, username="alice")
    await client.post("/api/auth/logout")
    bob = await register_and_login(client, db_session, username="bob", password="password123")
    # Give bob a display name so the partner payload's precedence is checked
    # for something other than the fallback username.
    await client.patch("/api/auth/me", json={"display_name": "Bobby"})

    dm = (await client.post("/api/rooms/dm", json={"other_user_id": alice["id"]})).json()

    await client.post("/api/auth/logout")
    await login_as(client, "alice")
    mine = (await client.get("/api/rooms/mine")).json()
    dm_entry = next(r for r in mine if r["id"] == dm["id"])
    assert dm_entry["is_dm"] is True
    assert dm_entry["dm_partner"]["user_id"] == bob["id"]
    assert dm_entry["dm_partner"]["username"] == "bob"
    assert dm_entry["dm_partner"]["display_name"] == "Bobby"

    # A regular room's dm_partner is always null.
    room = (await client.post("/api/rooms", json={"name": "general"})).json()
    mine = (await client.get("/api/rooms/mine")).json()
    room_entry = next(r for r in mine if r["id"] == room["id"])
    assert room_entry["is_dm"] is False
    assert room_entry["dm_partner"] is None


async def test_dm_cannot_be_updated(client, db_session):
    alice = await register_and_login(client, db_session, username="alice")
    await client.post("/api/auth/logout")
    bob = await register_and_login(client, db_session, username="bob")
    dm = (await client.post("/api/rooms/dm", json={"other_user_id": alice["id"]})).json()

    # bob is a plain 'member' of the DM (no admin/owner role exists for a
    # DM), so this 403s on the ordinary role gate before ever reaching
    # update_room's own is_dm guard.
    resp = await client.patch(f"/api/rooms/{dm['id']}", json={"name": "renamed"})
    assert resp.status_code == 403

    # A site admin bypasses that role gate (see #48) -- confirms the
    # explicit is_dm guard inside update_room itself is what stops this,
    # not just incidental role-based protection.
    await client.post("/api/auth/logout")
    admin = await register_and_login(client, db_session, username="carol")
    from app.models import User

    user = await db_session.get(User, uuid.UUID(admin["id"]))
    user.is_site_admin = True
    await db_session.commit()
    resp = await client.patch(f"/api/rooms/{dm['id']}", json={"name": "renamed"})
    assert resp.status_code == 400


async def test_dm_rejects_add_member_and_join(client, db_session):
    alice = await register_and_login(client, db_session, username="alice")
    await client.post("/api/auth/logout")
    bob = await register_and_login(client, db_session, username="bob")
    dm = (await client.post("/api/rooms/dm", json={"other_user_id": alice["id"]})).json()

    await client.post("/api/auth/logout")
    carol = await register_and_login(client, db_session, username="carol")

    # Neither participant has admin/owner role in a DM, so adding a third
    # person 403s on the existing role gate.
    await client.post("/api/auth/logout")
    await login_as(client, "bob")
    resp = await client.post(f"/api/rooms/{dm['id']}/members", json={"user_id": carol["id"]})
    assert resp.status_code == 403

    # is_private=True on the DM already blocks the plain join endpoint too.
    await client.post("/api/auth/logout")
    await login_as(client, "carol")
    resp = await client.post(f"/api/rooms/{dm['id']}/join")
    assert resp.status_code == 400


async def test_hide_dm_removes_it_from_mine_for_that_user_only(client, db_session):
    alice = await register_and_login(client, db_session, username="alice")
    await client.post("/api/auth/logout")
    bob = await register_and_login(client, db_session, username="bob")
    dm = (await client.post("/api/rooms/dm", json={"other_user_id": alice["id"]})).json()

    resp = await client.post(f"/api/rooms/{dm['id']}/hide")
    assert resp.status_code == 204

    mine = (await client.get("/api/rooms/mine")).json()
    assert all(r["id"] != dm["id"] for r in mine)

    # Alice never hid it -- still sees it, proving this is per-viewer, not
    # something that touched the room or bob's membership for everyone.
    await client.post("/api/auth/logout")
    await login_as(client, "alice")
    mine = (await client.get("/api/rooms/mine")).json()
    assert any(r["id"] == dm["id"] for r in mine)


async def test_hide_dm_rejects_regular_rooms(client, db_session):
    await register_and_login(client, db_session, username="alice")
    room = (await client.post("/api/rooms", json={"name": "general"})).json()
    resp = await client.post(f"/api/rooms/{room['id']}/hide")
    assert resp.status_code == 400


async def test_starting_a_dm_again_unhides_it(client, db_session):
    alice = await register_and_login(client, db_session, username="alice")
    await client.post("/api/auth/logout")
    bob = await register_and_login(client, db_session, username="bob")
    dm = (await client.post("/api/rooms/dm", json={"other_user_id": alice["id"]})).json()

    await client.post(f"/api/rooms/{dm['id']}/hide")
    mine = (await client.get("/api/rooms/mine")).json()
    assert all(r["id"] != dm["id"] for r in mine)

    # bob clicking alice in the People list again -- find_or_create_dm
    # resolves to the same room and un-hides it for him.
    resp = await client.post("/api/rooms/dm", json={"other_user_id": alice["id"]})
    assert resp.status_code == 201
    assert resp.json()["id"] == dm["id"]

    mine = (await client.get("/api/rooms/mine")).json()
    assert any(r["id"] == dm["id"] for r in mine)


def test_new_message_unhides_dm_for_both_participants(ws_client):
    alice = _register_ws(ws_client, _unique("alice"))
    bob = _register_ws(ws_client, _unique("bob"))  # ws_client is now logged in as bob
    dm = ws_client.post("/api/rooms/dm", json={"other_user_id": alice["id"]}).json()

    ws_client.post(f"/api/rooms/{dm['id']}/hide")
    assert all(r["id"] != dm["id"] for r in ws_client.get("/api/rooms/mine").json())

    ws_client.post(
        "/api/auth/login", json={"username_or_email": alice["username"], "password": "password123"}
    )
    with ws_client.websocket_connect("/ws/chat") as ws:
        ws.send_json({"type": "join", "room_id": dm["id"]})
        assert ws.receive_json()["type"] == "joined"
        ws.send_json({"type": "message", "room_id": dm["id"], "content": "you there?"})
        ws.receive_json()
        # Sync barrier (see test_mentions.py's identical helper): the
        # message ack only proves the room-level broadcast happened, not
        # that broadcast_new_message's own continuation (which un-hides
        # the room) has finished -- a second frame's own ack proves that.
        ws.send_json({"type": "join", "room_id": dm["id"]})
        assert ws.receive_json()["type"] == "joined"

    # bob never re-opened the DM himself -- alice's message alone unhid it.
    ws_client.post(
        "/api/auth/login", json={"username_or_email": bob["username"], "password": "password123"}
    )
    assert any(r["id"] == dm["id"] for r in ws_client.get("/api/rooms/mine").json())
