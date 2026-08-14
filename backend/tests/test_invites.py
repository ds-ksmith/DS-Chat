import uuid
from datetime import datetime, timedelta, timezone

from app.models import RoomInvite, User
from tests.conftest import login_as, register_and_login


async def _make_admin(db_session, user_id: str) -> None:
    user = await db_session.get(User, uuid.UUID(user_id))
    user.is_site_admin = True
    await db_session.commit()


async def _configure_smtp(client):
    resp = await client.put(
        "/api/admin/settings/smtp",
        json={
            "host": "smtp.example.com",
            "port": 587,
            "from_address": "noreply@example.com",
        },
    )
    assert resp.status_code == 200, resp.text


async def _create_private_room(client, name="secret"):
    resp = await client.post("/api/rooms", json={"name": name, "is_private": True})
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_create_invite_requires_admin(client, db_session):
    await register_and_login(client, db_session, username="alice")
    room = await _create_private_room(client)

    await client.post("/api/auth/logout")
    await register_and_login(client, db_session, username="bob")
    await register_and_login(client, db_session, username="carol")

    # bob has no membership in the room at all, so he's blocked by the
    # membership check before role is even considered.
    resp = await client.post(
        f"/api/rooms/{room['id']}/invites", json={"target_username": "carol"}
    )
    assert resp.status_code == 403


async def test_invite_unknown_username_404(client, db_session):
    await register_and_login(client, db_session, username="alice")
    room = await _create_private_room(client)

    resp = await client.post(
        f"/api/rooms/{room['id']}/invites", json={"target_username": "nobody"}
    )
    assert resp.status_code == 404


async def test_invite_accept_flow(client, db_session):
    await register_and_login(client, db_session, username="alice")
    room = await _create_private_room(client)
    await register_and_login(client, db_session, username="bob")  # seed bob's account only

    await login_as(client, "alice")
    resp = await client.post(
        f"/api/rooms/{room['id']}/invites", json={"target_username": "bob"}
    )
    assert resp.status_code == 201
    invite = resp.json()
    assert invite["status"] == "pending"
    assert invite["target_username"] == "bob"

    resp = await client.get(f"/api/rooms/{room['id']}/invites")
    assert resp.status_code == 200
    assert resp.json()[0]["target_username"] == "bob"

    await client.post("/api/auth/logout")
    await login_as(client, "bob")

    resp = await client.get("/api/invites/mine")
    assert resp.status_code == 200
    mine = resp.json()
    assert len(mine) == 1
    assert mine[0]["id"] == invite["id"]
    assert mine[0]["room_name"] == room["name"]
    assert mine[0]["invited_by_username"] == "alice"

    resp = await client.post(f"/api/invites/{invite['id']}/accept")
    assert resp.status_code == 200
    assert resp.json()["role"] == "member"

    resp = await client.get(f"/api/rooms/{room['id']}/messages")
    assert resp.status_code == 200  # now a member

    resp = await client.get("/api/rooms/mine")
    assert any(r["name"] == room["name"] for r in resp.json())


async def test_accept_invite_wrong_user_403(client, db_session):
    await register_and_login(client, db_session, username="alice")
    room = await _create_private_room(client)
    await register_and_login(client, db_session, username="bob")
    await login_as(client, "alice")
    invite = (
        await client.post(f"/api/rooms/{room['id']}/invites", json={"target_username": "bob"})
    ).json()

    await client.post("/api/auth/logout")
    await register_and_login(client, db_session, username="carol")
    resp = await client.post(f"/api/invites/{invite['id']}/accept")
    assert resp.status_code == 403


async def test_decline_invite(client, db_session):
    await register_and_login(client, db_session, username="alice")
    room = await _create_private_room(client)
    await register_and_login(client, db_session, username="bob")
    await login_as(client, "alice")
    invite = (
        await client.post(f"/api/rooms/{room['id']}/invites", json={"target_username": "bob"})
    ).json()

    await client.post("/api/auth/logout")
    await login_as(client, "bob")
    resp = await client.post(f"/api/invites/{invite['id']}/decline")
    assert resp.status_code == 200
    assert resp.json()["status"] == "revoked"

    resp = await client.post(f"/api/invites/{invite['id']}/accept")
    assert resp.status_code == 400  # no longer pending


async def test_revoke_invite(client, db_session):
    await register_and_login(client, db_session, username="alice")
    room = await _create_private_room(client)
    await register_and_login(client, db_session, username="bob")
    await login_as(client, "alice")
    invite = (
        await client.post(f"/api/rooms/{room['id']}/invites", json={"target_username": "bob"})
    ).json()

    resp = await client.delete(f"/api/rooms/{room['id']}/invites/{invite['id']}")
    assert resp.status_code == 204

    await client.post("/api/auth/logout")
    await login_as(client, "bob")
    resp = await client.post(f"/api/invites/{invite['id']}/accept")
    assert resp.status_code == 400


async def test_duplicate_pending_invite_rejected(client, db_session):
    await register_and_login(client, db_session, username="alice")
    room = await _create_private_room(client)
    await register_and_login(client, db_session, username="bob")
    await login_as(client, "alice")

    resp1 = await client.post(
        f"/api/rooms/{room['id']}/invites", json={"target_username": "bob"}
    )
    assert resp1.status_code == 201
    resp2 = await client.post(
        f"/api/rooms/{room['id']}/invites", json={"target_username": "bob"}
    )
    assert resp2.status_code == 409


async def test_invite_already_member_rejected(client, db_session):
    await register_and_login(client, db_session, username="alice")
    room = await _create_private_room(client, name="open-ish")
    resp = await client.post(
        f"/api/rooms/{room['id']}/invites", json={"target_username": "alice"}
    )
    assert resp.status_code == 409


async def test_expired_invite_rejected_on_accept(client, db_session):
    await register_and_login(client, db_session, username="alice")
    room = await _create_private_room(client)
    await register_and_login(client, db_session, username="bob")
    await login_as(client, "alice")
    invite = (
        await client.post(f"/api/rooms/{room['id']}/invites", json={"target_username": "bob"})
    ).json()

    db_invite = await db_session.get(RoomInvite, uuid.UUID(invite["id"]))
    db_invite.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
    await db_session.commit()

    await client.post("/api/auth/logout")
    await login_as(client, "bob")
    resp = await client.post(f"/api/invites/{invite['id']}/accept")
    assert resp.status_code == 400


async def test_create_invite_sends_email_to_target(client, db_session, monkeypatch):
    calls = []

    async def fake_send(message, **kwargs):
        calls.append(kwargs)

    monkeypatch.setattr("app.services.email_service.aiosmtplib.send", fake_send)

    alice = await register_and_login(client, db_session, username="alice")
    await _make_admin(db_session, alice["id"])
    await _configure_smtp(client)
    room = await _create_private_room(client)
    await register_and_login(client, db_session, username="bob")
    await login_as(client, "alice")

    resp = await client.post(
        f"/api/rooms/{room['id']}/invites", json={"target_username": "bob"}
    )
    assert resp.status_code == 201
    assert len(calls) == 1
    assert calls[0]["hostname"] == "smtp.example.com"


async def test_create_invite_succeeds_even_if_email_delivery_fails(client, db_session, monkeypatch):
    async def fake_send(message, **kwargs):
        raise ConnectionRefusedError("boom")

    monkeypatch.setattr("app.services.email_service.aiosmtplib.send", fake_send)

    alice = await register_and_login(client, db_session, username="alice")
    await _make_admin(db_session, alice["id"])
    await _configure_smtp(client)
    room = await _create_private_room(client)
    await register_and_login(client, db_session, username="bob")
    await login_as(client, "alice")

    resp = await client.post(
        f"/api/rooms/{room['id']}/invites", json={"target_username": "bob"}
    )
    assert resp.status_code == 201
