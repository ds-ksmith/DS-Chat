import re
import uuid
from datetime import datetime, timedelta, timezone

from app.models import SiteInvite, User
from tests.conftest import login_as, register_and_login


async def _make_admin(db_session, user_id: str) -> None:
    user = await db_session.get(User, uuid.UUID(user_id))
    user.is_site_admin = True
    await db_session.commit()


def _fake_smtp(monkeypatch):
    calls = []

    async def fake_send(message, **kwargs):
        calls.append({"message": message, **kwargs})

    monkeypatch.setattr("app.services.email_service.aiosmtplib.send", fake_send)
    return calls


async def _configure_smtp(client):
    resp = await client.put(
        "/api/admin/settings/smtp",
        json={
            "host": "smtp.example.com",
            "port": 587,
            "username": "bot",
            "password": "secret",
            "from_address": "noreply@example.com",
            "use_tls": True,
        },
    )
    assert resp.status_code == 200, resp.text


def _extract_token(body: str) -> str:
    match = re.search(r"token=([^\s&]+)", body)
    assert match, f"no token found in email body: {body}"
    return match.group(1)


async def test_create_site_invite_requires_admin(client, db_session):
    await register_and_login(client, db_session, username="alice")
    resp = await client.post("/api/admin/invites", json={"email": "newperson@example.com"})
    assert resp.status_code == 403


async def test_signup_flow_end_to_end(client, db_session, monkeypatch):
    calls = _fake_smtp(monkeypatch)
    admin = await register_and_login(client, db_session, username="admin1")
    await _make_admin(db_session, admin["id"])
    await _configure_smtp(client)

    resp = await client.post("/api/admin/invites", json={"email": "newperson@example.com"})
    assert resp.status_code == 201, resp.text
    invite = resp.json()
    assert invite["email"] == "newperson@example.com"
    assert invite["status"] == "pending"

    assert len(calls) == 1
    token = _extract_token(calls[0]["message"].get_content())

    validate = await client.get(f"/api/signup/validate?token={token}")
    assert validate.status_code == 200
    assert validate.json()["email"] == "newperson@example.com"

    complete = await client.post(
        "/api/signup",
        json={"token": token, "username": "newperson", "password": "password123"},
    )
    assert complete.status_code == 200, complete.text
    assert complete.json()["email"] == "newperson@example.com"

    me = await client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["username"] == "newperson"


async def test_invalid_token_rejected(client, db_session):
    await register_and_login(client, db_session, username="alice")

    validate = await client.get("/api/signup/validate?token=not-a-real-token")
    assert validate.status_code == 400

    complete = await client.post(
        "/api/signup",
        json={"token": "not-a-real-token", "username": "someone", "password": "password123"},
    )
    assert complete.status_code == 400


async def test_expired_token_rejected(client, db_session, monkeypatch):
    calls = _fake_smtp(monkeypatch)
    admin = await register_and_login(client, db_session, username="admin1")
    await _make_admin(db_session, admin["id"])
    await _configure_smtp(client)

    resp = await client.post("/api/admin/invites", json={"email": "late@example.com"})
    invite_id = resp.json()["id"]
    token = _extract_token(calls[0]["message"].get_content())

    db_invite = await db_session.get(SiteInvite, uuid.UUID(invite_id))
    db_invite.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
    await db_session.commit()

    complete = await client.post(
        "/api/signup",
        json={"token": token, "username": "late", "password": "password123"},
    )
    assert complete.status_code == 400


async def test_used_token_cannot_be_reused(client, db_session, monkeypatch):
    calls = _fake_smtp(monkeypatch)
    admin = await register_and_login(client, db_session, username="admin1")
    await _make_admin(db_session, admin["id"])
    await _configure_smtp(client)

    await client.post("/api/admin/invites", json={"email": "once@example.com"})
    token = _extract_token(calls[0]["message"].get_content())

    first = await client.post(
        "/api/signup",
        json={"token": token, "username": "onceuser", "password": "password123"},
    )
    assert first.status_code == 200

    second = await client.post(
        "/api/signup",
        json={"token": token, "username": "onceuser2", "password": "password123"},
    )
    assert second.status_code == 400


async def test_revoke_site_invite_prevents_signup(client, db_session, monkeypatch):
    calls = _fake_smtp(monkeypatch)
    admin = await register_and_login(client, db_session, username="admin1")
    await _make_admin(db_session, admin["id"])
    await _configure_smtp(client)

    resp = await client.post("/api/admin/invites", json={"email": "revoked@example.com"})
    invite_id = resp.json()["id"]
    token = _extract_token(calls[0]["message"].get_content())

    revoke = await client.delete(f"/api/admin/invites/{invite_id}")
    assert revoke.status_code == 200
    assert revoke.json()["status"] == "revoked"

    complete = await client.post(
        "/api/signup",
        json={"token": token, "username": "revokeduser", "password": "password123"},
    )
    assert complete.status_code == 400


async def test_list_site_invites(client, db_session, monkeypatch):
    _fake_smtp(monkeypatch)
    admin = await register_and_login(client, db_session, username="admin1")
    await _make_admin(db_session, admin["id"])
    await _configure_smtp(client)

    await client.post("/api/admin/invites", json={"email": "listed@example.com"})
    resp = await client.get("/api/admin/invites")
    assert resp.status_code == 200
    emails = [i["email"] for i in resp.json()]
    assert "listed@example.com" in emails
