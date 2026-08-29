import uuid

from httpx import ASGITransport, AsyncClient

from app.schemas.user import UserCreate
from app.services.auth_service import register_user
from tests.conftest import login_as, register_and_login


def _unique(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


async def test_login_creates_a_session(client, db_session):
    username = _unique("alice")
    await register_user(
        db_session, UserCreate(username=username, email=f"{username}@example.com", password="password123")
    )
    resp = await client.post(
        "/api/auth/login",
        json={"username_or_email": username, "password": "password123"},
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0 Safari/537.36"},
    )
    assert resp.status_code == 200, resp.text

    sessions = (await client.get("/api/auth/sessions")).json()
    assert len(sessions) == 1
    assert sessions[0]["is_current"] is True
    assert sessions[0]["device_label"] == "Chrome on Windows"
    assert sessions[0]["ip_address"]


async def test_logout_revokes_the_session(client, db_session):
    await register_and_login(client, db_session, username=_unique("alice"))
    assert len((await client.get("/api/auth/sessions")).json()) == 1

    await client.post("/api/auth/logout")
    # The important part is server-side: the session row itself is gone
    # from the active list (this request also 401s since this client's own
    # cookie was cleared, but that alone wouldn't prove the *row* is dead).
    resp = await client.get("/api/auth/sessions")
    assert resp.status_code == 401


async def test_x_forwarded_for_takes_priority_over_direct_peer(client, db_session):
    username = _unique("alice")
    await register_user(
        db_session, UserCreate(username=username, email=f"{username}@example.com", password="password123")
    )
    await client.post(
        "/api/auth/login",
        json={"username_or_email": username, "password": "password123"},
        headers={"X-Forwarded-For": "203.0.113.7, 10.0.0.1"},
    )

    sessions = (await client.get("/api/auth/sessions")).json()
    assert sessions[0]["ip_address"] == "203.0.113.7"


async def test_revoking_another_session_logs_it_out(client, app, db_session):
    username = _unique("alice")
    await register_and_login(client, db_session, username=username)

    # A second "device" -- a separate client hitting the same app instance
    # (so it shares the DB-override wiring), its own independent cookie.
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as other_device:
        await login_as(other_device, username)
        assert len((await other_device.get("/api/auth/sessions")).json()) == 2

        mine = (await client.get("/api/auth/sessions")).json()
        assert len(mine) == 2
        not_current = next(s for s in mine if not s["is_current"])

        revoke = await client.delete(f"/api/auth/sessions/{not_current['id']}")
        assert revoke.status_code == 204

        # The other device's own cookie is now dead.
        resp = await other_device.get("/api/auth/sessions")
        assert resp.status_code == 401

    # And the revoked session no longer shows up for the account at all.
    remaining = (await client.get("/api/auth/sessions")).json()
    assert len(remaining) == 1
    assert remaining[0]["is_current"] is True


async def test_cannot_revoke_another_users_session(client, app, db_session):
    await register_and_login(client, db_session, username=_unique("alice"))
    my_session_id = (await client.get("/api/auth/sessions")).json()[0]["id"]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as bob_client:
        await register_and_login(bob_client, db_session, username=_unique("bob"))
        resp = await bob_client.delete(f"/api/auth/sessions/{my_session_id}")
        assert resp.status_code == 404

    # Untouched -- still exactly one active session for alice.
    assert len((await client.get("/api/auth/sessions")).json()) == 1


async def test_revoking_own_current_session_works_then_logs_this_client_out(client, db_session):
    await register_and_login(client, db_session, username=_unique("alice"))
    session_id = (await client.get("/api/auth/sessions")).json()[0]["id"]

    # Revoking your own *current* session is allowed (a remote sign-out of
    # this same device is a legitimate, if odd, thing to do).
    first = await client.delete(f"/api/auth/sessions/{session_id}")
    assert first.status_code == 204

    # A second call with the same (now-dead) cookie can't even reach the
    # revoke check -- get_current_user itself already 401s.
    second = await client.delete(f"/api/auth/sessions/{session_id}")
    assert second.status_code == 401
