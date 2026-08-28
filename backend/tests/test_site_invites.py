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


def _plain_text(message) -> str:
    # #68: the email is now multipart/alternative (HTML + plain-text
    # fallback) -- .get_content() has no handler for a multipart message
    # itself, get_body(preferencelist=...) is the standard way to reach a
    # specific alternative part.
    return message.get_body(preferencelist=("plain",)).get_content()


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
    token = _extract_token(_plain_text(calls[0]["message"]))

    validate = await client.get(f"/api/signup/validate?token={token}")
    assert validate.status_code == 200
    assert validate.json()["email"] == "newperson@example.com"

    complete = await client.post(
        "/api/signup",
        json={"token": token, "username": "newperson", "password": "password123", "password_confirm": "password123"},
    )
    assert complete.status_code == 200, complete.text
    assert complete.json()["email"] == "newperson@example.com"

    me = await client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["username"] == "newperson"


async def test_signup_rejects_mismatched_password_confirmation(client, db_session, monkeypatch):
    calls = _fake_smtp(monkeypatch)
    admin = await register_and_login(client, db_session, username="admin1")
    await _make_admin(db_session, admin["id"])
    await _configure_smtp(client)

    await client.post("/api/admin/invites", json={"email": "typo@example.com"})
    token = _extract_token(_plain_text(calls[0]["message"]))

    complete = await client.post(
        "/api/signup",
        json={
            "token": token,
            "username": "typouser",
            "password": "password123",
            "password_confirm": "password124",
        },
    )
    assert complete.status_code == 422

    # The mismatch must not have consumed the invite -- a typo shouldn't
    # burn a single-use token.
    validate = await client.get(f"/api/signup/validate?token={token}")
    assert validate.status_code == 200


async def test_invalid_token_rejected(client, db_session):
    await register_and_login(client, db_session, username="alice")

    validate = await client.get("/api/signup/validate?token=not-a-real-token")
    assert validate.status_code == 400

    complete = await client.post(
        "/api/signup",
        json={"token": "not-a-real-token", "username": "someone", "password": "password123", "password_confirm": "password123"},
    )
    assert complete.status_code == 400


async def test_expired_token_rejected(client, db_session, monkeypatch):
    calls = _fake_smtp(monkeypatch)
    admin = await register_and_login(client, db_session, username="admin1")
    await _make_admin(db_session, admin["id"])
    await _configure_smtp(client)

    resp = await client.post("/api/admin/invites", json={"email": "late@example.com"})
    invite_id = resp.json()["id"]
    token = _extract_token(_plain_text(calls[0]["message"]))

    db_invite = await db_session.get(SiteInvite, uuid.UUID(invite_id))
    db_invite.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
    await db_session.commit()

    complete = await client.post(
        "/api/signup",
        json={"token": token, "username": "late", "password": "password123", "password_confirm": "password123"},
    )
    assert complete.status_code == 400


async def test_used_token_cannot_be_reused(client, db_session, monkeypatch):
    calls = _fake_smtp(monkeypatch)
    admin = await register_and_login(client, db_session, username="admin1")
    await _make_admin(db_session, admin["id"])
    await _configure_smtp(client)

    await client.post("/api/admin/invites", json={"email": "once@example.com"})
    token = _extract_token(_plain_text(calls[0]["message"]))

    first = await client.post(
        "/api/signup",
        json={"token": token, "username": "onceuser", "password": "password123", "password_confirm": "password123"},
    )
    assert first.status_code == 200

    second = await client.post(
        "/api/signup",
        json={"token": token, "username": "onceuser2", "password": "password123", "password_confirm": "password123"},
    )
    assert second.status_code == 400


async def test_revoke_site_invite_prevents_signup(client, db_session, monkeypatch):
    calls = _fake_smtp(monkeypatch)
    admin = await register_and_login(client, db_session, username="admin1")
    await _make_admin(db_session, admin["id"])
    await _configure_smtp(client)

    resp = await client.post("/api/admin/invites", json={"email": "revoked@example.com"})
    invite_id = resp.json()["id"]
    token = _extract_token(_plain_text(calls[0]["message"]))

    revoke = await client.delete(f"/api/admin/invites/{invite_id}")
    assert revoke.status_code == 200
    assert revoke.json()["status"] == "revoked"

    complete = await client.post(
        "/api/signup",
        json={"token": token, "username": "revokeduser", "password": "password123", "password_confirm": "password123"},
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


async def test_list_site_invites_excludes_revoked_invite(client, db_session, monkeypatch):
    # #61: the admin UI labels this list "Pending invites" -- a revoked
    # invite has nothing left to act on and must actually drop out of it,
    # not just get relabeled in place.
    _fake_smtp(monkeypatch)
    admin = await register_and_login(client, db_session, username="admin1")
    await _make_admin(db_session, admin["id"])
    await _configure_smtp(client)

    resp = await client.post("/api/admin/invites", json={"email": "revoked-from-list@example.com"})
    invite_id = resp.json()["id"]

    revoke = await client.delete(f"/api/admin/invites/{invite_id}")
    assert revoke.status_code == 200

    listed = await client.get("/api/admin/invites")
    emails = [i["email"] for i in listed.json()]
    assert "revoked-from-list@example.com" not in emails


async def test_list_site_invites_excludes_accepted_invite(client, db_session, monkeypatch):
    # Same gap, the other trigger: completing signup accepts the invite
    # out-of-band from the admin's own session, but it must still be gone
    # from the pending list on the admin's next fetch.
    calls = _fake_smtp(monkeypatch)
    admin = await register_and_login(client, db_session, username="admin1")
    await _make_admin(db_session, admin["id"])
    await _configure_smtp(client)

    await client.post("/api/admin/invites", json={"email": "accepted-from-list@example.com"})
    token = _extract_token(_plain_text(calls[0]["message"]))

    complete = await client.post(
        "/api/signup",
        json={
            "token": token,
            "username": "acceptedfromlist",
            "password": "password123",
            "password_confirm": "password123",
        },
    )
    assert complete.status_code == 200, complete.text

    # Signup logs the new user's session in on `client` -- switch back to
    # the admin to check the list the way the admin actually would.
    await login_as(client, "admin1")
    listed = await client.get("/api/admin/invites")
    emails = [i["email"] for i in listed.json()]
    assert "accepted-from-list@example.com" not in emails
