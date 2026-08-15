import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.models import PasswordReset
from tests.conftest import register_and_login


def _fake_send_email(monkeypatch):
    calls = []

    async def fake(db, to, subject, body):
        calls.append({"to": to, "subject": subject, "body": body})

    monkeypatch.setattr("app.services.password_service.send_email", fake)
    return calls


def _extract_token(body: str) -> str:
    match = re.search(r"token=([^\s&]+)", body)
    assert match, f"no token found in email body: {body}"
    return match.group(1)


async def test_change_password_requires_auth(client):
    resp = await client.patch(
        "/api/auth/password", json={"current_password": "x", "new_password": "newpassword123"}
    )
    assert resp.status_code == 401


async def test_change_password_wrong_current(client, db_session):
    await register_and_login(client, db_session, username="alice")
    resp = await client.patch(
        "/api/auth/password",
        json={"current_password": "wrong-password", "new_password": "newpassword123"},
    )
    assert resp.status_code == 400


async def test_change_password_success(client, db_session):
    await register_and_login(client, db_session, username="alice")
    resp = await client.patch(
        "/api/auth/password",
        json={"current_password": "password123", "new_password": "newpassword123"},
    )
    assert resp.status_code == 204

    await client.post("/api/auth/logout")
    old = await client.post(
        "/api/auth/login", json={"username_or_email": "alice", "password": "password123"}
    )
    assert old.status_code == 401
    new = await client.post(
        "/api/auth/login", json={"username_or_email": "alice", "password": "newpassword123"}
    )
    assert new.status_code == 200


async def test_change_password_too_short_rejected(client, db_session):
    await register_and_login(client, db_session, username="alice")
    resp = await client.patch(
        "/api/auth/password",
        json={"current_password": "password123", "new_password": "short"},
    )
    assert resp.status_code == 422


async def test_forgot_password_unknown_email_no_email_sent(client, monkeypatch):
    calls = _fake_send_email(monkeypatch)
    resp = await client.post("/api/auth/forgot-password", json={"email": "nobody@example.com"})
    assert resp.status_code == 204
    assert calls == []


async def test_forgot_password_known_email_sends_email(client, db_session, monkeypatch):
    calls = _fake_send_email(monkeypatch)
    await register_and_login(client, db_session, username="alice")
    await client.post("/api/auth/logout")

    resp = await client.post("/api/auth/forgot-password", json={"email": "alice@example.com"})
    assert resp.status_code == 204
    assert len(calls) == 1
    assert calls[0]["to"] == "alice@example.com"


async def test_reset_password_flow_end_to_end(client, db_session, monkeypatch):
    calls = _fake_send_email(monkeypatch)
    await register_and_login(client, db_session, username="alice")
    await client.post("/api/auth/logout")

    await client.post("/api/auth/forgot-password", json={"email": "alice@example.com"})
    token = _extract_token(calls[0]["body"])

    validate = await client.get(f"/api/auth/reset-password/validate?token={token}")
    assert validate.status_code == 204

    complete = await client.post(
        "/api/auth/reset-password", json={"token": token, "new_password": "brandnewpass123"}
    )
    assert complete.status_code == 200
    assert complete.json()["username"] == "alice"

    # completing a reset logs the user in immediately, same as signup
    me = await client.get("/api/auth/me")
    assert me.status_code == 200

    await client.post("/api/auth/logout")
    old = await client.post(
        "/api/auth/login", json={"username_or_email": "alice", "password": "password123"}
    )
    assert old.status_code == 401
    new = await client.post(
        "/api/auth/login", json={"username_or_email": "alice", "password": "brandnewpass123"}
    )
    assert new.status_code == 200


async def test_reset_password_invalid_token_rejected(client):
    resp = await client.get("/api/auth/reset-password/validate?token=not-a-real-token")
    assert resp.status_code == 400

    complete = await client.post(
        "/api/auth/reset-password",
        json={"token": "not-a-real-token", "new_password": "newpassword123"},
    )
    assert complete.status_code == 400


async def test_reset_password_expired_token_rejected(client, db_session, monkeypatch):
    calls = _fake_send_email(monkeypatch)
    await register_and_login(client, db_session, username="alice")
    await client.post("/api/auth/logout")
    await client.post("/api/auth/forgot-password", json={"email": "alice@example.com"})
    token = _extract_token(calls[0]["body"])

    reset = (await db_session.execute(select(PasswordReset))).scalar_one()
    reset.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    await db_session.commit()

    complete = await client.post(
        "/api/auth/reset-password", json={"token": token, "new_password": "newpassword123"}
    )
    assert complete.status_code == 400


async def test_reset_password_used_token_cannot_be_reused(client, db_session, monkeypatch):
    calls = _fake_send_email(monkeypatch)
    await register_and_login(client, db_session, username="alice")
    await client.post("/api/auth/logout")
    await client.post("/api/auth/forgot-password", json={"email": "alice@example.com"})
    token = _extract_token(calls[0]["body"])

    first = await client.post(
        "/api/auth/reset-password", json={"token": token, "new_password": "firstpass123"}
    )
    assert first.status_code == 200

    second = await client.post(
        "/api/auth/reset-password", json={"token": token, "new_password": "secondpass123"}
    )
    assert second.status_code == 400
