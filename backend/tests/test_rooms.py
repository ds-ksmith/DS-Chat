import uuid

from sqlalchemy import select

from app.models import Room, RoomMembership, RoomRole
from tests.conftest import register_and_login


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
