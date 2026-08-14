import uuid

from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.models import AdminAuditLog, User
from app.schemas.user import UserCreate
from app.services.auth_service import register_user
from tests.conftest import login_as, register_and_login


async def _make_admin(db_session, user_id: str) -> None:
    user = await db_session.get(User, uuid.UUID(user_id))
    user.is_site_admin = True
    await db_session.commit()


async def _create_user_direct(db_session, username: str) -> User:
    # Seed a target user without disturbing `client`'s active session --
    # same technique register_and_login uses under the hood, just without
    # the login step.
    return await register_user(
        db_session,
        UserCreate(username=username, email=f"{username}@example.com", password="password123"),
    )


async def test_admin_endpoints_require_site_admin(client, db_session):
    await register_and_login(client, db_session, username="alice")
    fake_id = uuid.uuid4()

    assert (await client.get("/api/admin/users")).status_code == 403
    assert (await client.get("/api/admin/rooms")).status_code == 403
    assert (await client.get("/api/admin/audit-log")).status_code == 403
    assert (await client.post(f"/api/admin/users/{fake_id}/deactivate")).status_code == 403


async def test_list_users_includes_target(client, db_session):
    admin = await register_and_login(client, db_session, username="admin1")
    await _make_admin(db_session, admin["id"])
    bob = await _create_user_direct(db_session, "bob")

    resp = await client.get("/api/admin/users")
    assert resp.status_code == 200
    usernames = {u["username"] for u in resp.json()}
    assert {"admin1", "bob"} <= usernames
    bob_entry = next(u for u in resp.json() if u["username"] == "bob")
    assert bob_entry["is_active"] is True


async def test_deactivate_and_reactivate_user(client, db_session):
    admin = await register_and_login(client, db_session, username="admin1")
    await _make_admin(db_session, admin["id"])
    bob = await _create_user_direct(db_session, "bob")

    resp = await client.post(f"/api/admin/users/{bob.id}/deactivate")
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False

    resp = await client.post(f"/api/admin/users/{bob.id}/reactivate")
    assert resp.status_code == 200
    assert resp.json()["is_active"] is True


async def test_deactivated_user_loses_access(client, db_session, app):
    alice = await register_and_login(client, db_session, username="alice")
    assert (await client.get("/api/auth/me")).status_code == 200

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as bob_client:
        bob = await register_and_login(bob_client, db_session, username="bob")
        await _make_admin(db_session, bob["id"])

        resp = await bob_client.post(f"/api/admin/users/{alice['id']}/deactivate")
        assert resp.status_code == 200
        assert resp.json()["is_active"] is False

    # An already-established session dies immediately -- get_current_user
    # rereads is_active on every request.
    assert (await client.get("/api/auth/me")).status_code == 401
    # A fresh login attempt is also rejected.
    login_resp = await client.post(
        "/api/auth/login", json={"username_or_email": "alice", "password": "password123"}
    )
    assert login_resp.status_code == 401


async def test_reset_password(client, db_session, app):
    admin = await register_and_login(client, db_session, username="admin1")
    await _make_admin(db_session, admin["id"])
    bob = await _create_user_direct(db_session, "bob")

    resp = await client.post(
        f"/api/admin/users/{bob.id}/reset-password", json={"new_password": "new-password-1"}
    )
    assert resp.status_code == 204

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as bob_client:
        old_login = await bob_client.post(
            "/api/auth/login", json={"username_or_email": "bob", "password": "password123"}
        )
        assert old_login.status_code == 401

        new_login = await bob_client.post(
            "/api/auth/login", json={"username_or_email": "bob", "password": "new-password-1"}
        )
        assert new_login.status_code == 200


async def test_promote_and_demote_user(client, db_session):
    admin = await register_and_login(client, db_session, username="admin1")
    await _make_admin(db_session, admin["id"])
    bob = await _create_user_direct(db_session, "bob")

    resp = await client.post(f"/api/admin/users/{bob.id}/promote")
    assert resp.status_code == 200
    assert resp.json()["is_site_admin"] is True

    resp = await client.post(f"/api/admin/users/{bob.id}/demote")
    assert resp.status_code == 200
    assert resp.json()["is_site_admin"] is False


async def test_cannot_deactivate_own_account(client, db_session):
    admin = await register_and_login(client, db_session, username="admin1")
    await _make_admin(db_session, admin["id"])

    resp = await client.post(f"/api/admin/users/{admin['id']}/deactivate")
    assert resp.status_code == 400


async def test_cannot_demote_own_account(client, db_session):
    admin = await register_and_login(client, db_session, username="admin1")
    await _make_admin(db_session, admin["id"])

    resp = await client.post(f"/api/admin/users/{admin['id']}/demote")
    assert resp.status_code == 400


async def test_list_rooms_includes_private_with_member_count(client, db_session):
    admin = await register_and_login(client, db_session, username="admin1")
    await _make_admin(db_session, admin["id"])

    await client.post("/api/rooms", json={"name": "open-room"})
    await client.post("/api/rooms", json={"name": "secret-room", "is_private": True})

    resp = await client.get("/api/admin/rooms")
    assert resp.status_code == 200
    rooms_by_name = {r["name"]: r for r in resp.json()}
    assert "secret-room" in rooms_by_name
    assert rooms_by_name["secret-room"]["is_private"] is True
    assert rooms_by_name["open-room"]["member_count"] == 1


async def test_archive_hides_room_from_open_browse_but_not_members(client, db_session):
    admin = await register_and_login(client, db_session, username="admin1")
    await _make_admin(db_session, admin["id"])
    room = (await client.post("/api/rooms", json={"name": "general"})).json()

    resp = await client.post(f"/api/admin/rooms/{room['id']}/archive")
    assert resp.status_code == 200
    assert resp.json()["is_archived"] is True

    open_rooms = (await client.get("/api/rooms")).json()
    assert not any(r["id"] == room["id"] for r in open_rooms)

    # existing member (the admin, as owner) can still read history
    messages_resp = await client.get(f"/api/rooms/{room['id']}/messages")
    assert messages_resp.status_code == 200

    resp = await client.post(f"/api/admin/rooms/{room['id']}/unarchive")
    assert resp.status_code == 200
    assert resp.json()["is_archived"] is False
    open_rooms = (await client.get("/api/rooms")).json()
    assert any(r["id"] == room["id"] for r in open_rooms)


async def test_transfer_ownership_admin(client, db_session):
    admin = await register_and_login(client, db_session, username="admin1")
    await _make_admin(db_session, admin["id"])
    room = (await client.post("/api/rooms", json={"name": "general"})).json()
    bob = await _create_user_direct(db_session, "bob")

    from app.services.room_service import join_room

    await join_room(db_session, uuid.UUID(room["id"]), bob.id)

    resp = await client.post(
        f"/api/admin/rooms/{room['id']}/transfer-ownership", json={"new_owner_id": str(bob.id)}
    )
    assert resp.status_code == 200
    assert resp.json()["owner_id"] == str(bob.id)


async def test_transfer_ownership_requires_existing_membership(client, db_session):
    admin = await register_and_login(client, db_session, username="admin1")
    await _make_admin(db_session, admin["id"])
    room = (await client.post("/api/rooms", json={"name": "general"})).json()
    bob = await _create_user_direct(db_session, "bob")

    resp = await client.post(
        f"/api/admin/rooms/{room['id']}/transfer-ownership", json={"new_owner_id": str(bob.id)}
    )
    assert resp.status_code == 400


async def test_admin_action_writes_audit_log(client, db_session):
    admin = await register_and_login(client, db_session, username="admin1")
    await _make_admin(db_session, admin["id"])
    bob = await _create_user_direct(db_session, "bob")

    resp = await client.post(f"/api/admin/users/{bob.id}/deactivate")
    assert resp.status_code == 200

    result = await db_session.execute(
        select(AdminAuditLog).where(AdminAuditLog.target_id == bob.id)
    )
    entries = result.scalars().all()
    assert len(entries) == 1
    assert entries[0].action == "user.deactivate"
    assert entries[0].actor_id == uuid.UUID(admin["id"])
    assert entries[0].target_type == "user"


async def test_audit_log_endpoint_lists_entries(client, db_session):
    admin = await register_and_login(client, db_session, username="admin1")
    await _make_admin(db_session, admin["id"])
    bob = await _create_user_direct(db_session, "bob")

    await client.post(f"/api/admin/users/{bob.id}/deactivate")

    resp = await client.get("/api/admin/audit-log")
    assert resp.status_code == 200
    entries = resp.json()
    assert any(
        e["action"] == "user.deactivate" and e["target_id"] == str(bob.id) for e in entries
    )
    assert entries[0]["actor_username"] == "admin1"
