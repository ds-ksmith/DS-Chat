import uuid

from sqlalchemy import select

from app.crypto import decrypt
from app.models import SmtpSettings, User
from tests.conftest import register_and_login


async def _get_settings_row(db_session) -> SmtpSettings:
    result = await db_session.execute(select(SmtpSettings))
    return result.scalar_one()


async def _make_admin(db_session, user_id: str) -> None:
    user = await db_session.get(User, uuid.UUID(user_id))
    user.is_site_admin = True
    await db_session.commit()


async def test_smtp_settings_require_admin(client, db_session):
    await register_and_login(client, db_session, username="alice")
    resp = await client.get("/api/admin/settings/smtp")
    assert resp.status_code == 403

    resp = await client.put(
        "/api/admin/settings/smtp",
        json={
            "host": "smtp.example.com",
            "port": 587,
            "from_address": "noreply@example.com",
        },
    )
    assert resp.status_code == 403


async def test_smtp_settings_get_before_configured(client, db_session):
    admin = await register_and_login(client, db_session, username="admin1")
    await _make_admin(db_session, admin["id"])

    resp = await client.get("/api/admin/settings/smtp")
    assert resp.status_code == 200
    assert resp.json() is None


async def test_smtp_settings_update_and_password_never_returned(client, db_session):
    admin = await register_and_login(client, db_session, username="admin1")
    await _make_admin(db_session, admin["id"])

    resp = await client.put(
        "/api/admin/settings/smtp",
        json={
            "host": "smtp.example.com",
            "port": 587,
            "username": "bot",
            "password": "super-secret",
            "from_address": "noreply@example.com",
            "use_tls": True,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "password" not in body
    assert body["has_password"] is True
    assert body["host"] == "smtp.example.com"

    get_resp = await client.get("/api/admin/settings/smtp")
    assert get_resp.status_code == 200
    assert "password" not in get_resp.json()
    assert get_resp.json()["has_password"] is True


async def test_smtp_settings_password_encrypted_at_rest(client, db_session):
    admin = await register_and_login(client, db_session, username="admin1")
    await _make_admin(db_session, admin["id"])

    await client.put(
        "/api/admin/settings/smtp",
        json={
            "host": "smtp.example.com",
            "port": 587,
            "password": "super-secret",
            "from_address": "noreply@example.com",
        },
    )

    row = await _get_settings_row(db_session)
    assert row.password_encrypted != "super-secret"
    assert decrypt(row.password_encrypted) == "super-secret"


async def test_smtp_settings_blank_password_keeps_existing(client, db_session):
    admin = await register_and_login(client, db_session, username="admin1")
    await _make_admin(db_session, admin["id"])

    await client.put(
        "/api/admin/settings/smtp",
        json={
            "host": "smtp.example.com",
            "port": 587,
            "password": "first-password",
            "from_address": "noreply@example.com",
        },
    )
    encrypted_before = (await _get_settings_row(db_session)).password_encrypted

    resp = await client.put(
        "/api/admin/settings/smtp",
        json={
            "host": "smtp.example.com",
            "port": 2525,
            "from_address": "noreply@example.com",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["port"] == 2525
    assert resp.json()["has_password"] is True

    row = await _get_settings_row(db_session)
    assert row.password_encrypted == encrypted_before


async def test_send_test_email_not_configured(client, db_session):
    admin = await register_and_login(client, db_session, username="admin1")
    await _make_admin(db_session, admin["id"])

    resp = await client.post("/api/admin/settings/smtp/test")
    assert resp.status_code == 400


async def test_send_test_email_success(client, db_session, monkeypatch):
    calls = []

    async def fake_send(message, **kwargs):
        calls.append(kwargs)

    monkeypatch.setattr("app.services.email_service.aiosmtplib.send", fake_send)

    admin = await register_and_login(client, db_session, username="admin1")
    await _make_admin(db_session, admin["id"])
    await client.put(
        "/api/admin/settings/smtp",
        json={
            "host": "smtp.example.com",
            "port": 587,
            "from_address": "noreply@example.com",
        },
    )

    resp = await client.post("/api/admin/settings/smtp/test")
    assert resp.status_code == 204
    assert len(calls) == 1
    assert calls[0]["hostname"] == "smtp.example.com"


async def test_send_test_email_surfaces_failure(client, db_session, monkeypatch):
    async def fake_send(message, **kwargs):
        raise ConnectionRefusedError("boom")

    monkeypatch.setattr("app.services.email_service.aiosmtplib.send", fake_send)

    admin = await register_and_login(client, db_session, username="admin1")
    await _make_admin(db_session, admin["id"])
    await client.put(
        "/api/admin/settings/smtp",
        json={
            "host": "smtp.example.com",
            "port": 587,
            "from_address": "noreply@example.com",
        },
    )

    resp = await client.post("/api/admin/settings/smtp/test")
    assert resp.status_code == 502
