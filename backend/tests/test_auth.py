import pytest

from app.schemas.user import UserCreate
from app.services.auth_service import DuplicateUserError, register_user
from tests.conftest import register_and_login


async def test_login_sets_session_and_me_returns_user(client, db_session):
    user = await register_and_login(client, db_session, username="alice")
    assert user["username"] == "alice"
    assert user["email"] == "alice@example.com"

    resp = await client.get("/api/auth/me")
    assert resp.status_code == 200
    assert resp.json()["id"] == user["id"]


async def test_login_wrong_password(client, db_session):
    data = UserCreate(username="erin", email="erin@example.com", password="password123")
    await register_user(db_session, data)

    resp = await client.post(
        "/api/auth/login",
        json={"username_or_email": "erin", "password": "wrong-password"},
    )
    assert resp.status_code == 401


async def test_login_unknown_user(client):
    resp = await client.post(
        "/api/auth/login",
        json={"username_or_email": "nobody", "password": "password123"},
    )
    assert resp.status_code == 401


async def test_me_requires_auth(client):
    resp = await client.get("/api/auth/me")
    assert resp.status_code == 401


async def test_logout_clears_session(client, db_session):
    await register_and_login(client, db_session, username="frank")
    resp = await client.post("/api/auth/logout")
    assert resp.status_code == 204

    resp = await client.get("/api/auth/me")
    assert resp.status_code == 401


async def test_register_user_duplicate_username_conflicts(db_session):
    await register_user(
        db_session, UserCreate(username="bob", email="bob@example.com", password="password123")
    )
    with pytest.raises(DuplicateUserError):
        await register_user(
            db_session,
            UserCreate(username="bob", email="different@example.com", password="password123"),
        )


async def test_register_user_duplicate_email_conflicts(db_session):
    await register_user(
        db_session, UserCreate(username="carol", email="carol@example.com", password="password123")
    )
    with pytest.raises(DuplicateUserError):
        await register_user(
            db_session,
            UserCreate(username="different", email="carol@example.com", password="password123"),
        )
