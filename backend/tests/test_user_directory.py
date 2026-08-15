import uuid

from app.models import User
from app.services.bot_service import create_bot
from tests.conftest import register_and_login


def _unique(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


async def _make_admin(db_session, user_id: str) -> None:
    user = await db_session.get(User, uuid.UUID(user_id))
    user.is_site_admin = True
    await db_session.commit()


async def test_user_directory_requires_auth(client):
    resp = await client.get("/api/users")
    assert resp.status_code == 401


async def test_user_directory_lists_active_users(client, db_session):
    alice = await register_and_login(client, db_session, username=_unique("alice"))
    await register_and_login(client, db_session, username=_unique("bob"))

    resp = await client.get("/api/users")
    assert resp.status_code == 200
    usernames = {u["username"] for u in resp.json()}
    assert alice["username"] in usernames
    entry = next(u for u in resp.json() if u["id"] == alice["id"])
    assert entry["display_name"] is None
    assert entry["avatar_filename"] is None


async def test_user_directory_excludes_bots(client, db_session):
    admin = await register_and_login(client, db_session, username=_unique("admin"))
    await _make_admin(db_session, admin["id"])
    admin_user = await db_session.get(User, uuid.UUID(admin["id"]))
    bot_username = _unique("bot")
    await create_bot(db_session, admin_user, bot_username)

    resp = await client.get("/api/users")
    usernames = {u["username"] for u in resp.json()}
    assert bot_username not in usernames


async def test_user_directory_excludes_deactivated_users(client, db_session):
    admin = await register_and_login(client, db_session, username=_unique("admin"))
    await _make_admin(db_session, admin["id"])
    bob = await register_and_login(client, db_session, username=_unique("bob"))

    await client.post("/api/auth/login", json={"username_or_email": admin["username"], "password": "password123"})
    await client.post(f"/api/admin/users/{bob['id']}/deactivate")

    resp = await client.get("/api/users")
    usernames = {u["username"] for u in resp.json()}
    assert bob["username"] not in usernames
