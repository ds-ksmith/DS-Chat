import uuid

from sqlalchemy import select

from app.models import AdminAuditLog, User
from tests.conftest import login_as, register_and_login


async def _make_admin(db_session, user_id: str) -> None:
    user = await db_session.get(User, uuid.UUID(user_id))
    user.is_site_admin = True
    await db_session.commit()


async def test_create_bot_requires_site_admin(client, db_session):
    await register_and_login(client, db_session, username="alice")
    resp = await client.post("/api/admin/bots", json={"username": "helper-bot"})
    assert resp.status_code == 403


async def test_create_bot_and_issue_token(client, db_session):
    admin = await register_and_login(client, db_session, username="admin1")
    await _make_admin(db_session, admin["id"])

    bot_resp = await client.post("/api/admin/bots", json={"username": "helper-bot"})
    assert bot_resp.status_code == 201
    bot = bot_resp.json()
    assert bot["username"] == "helper-bot"
    assert bot["is_active"] is True

    token_resp = await client.post(
        f"/api/admin/bots/{bot['id']}/tokens",
        json={"scopes": ["read:messages", "write:messages"]},
    )
    assert token_resp.status_code == 201
    token = token_resp.json()
    assert token["token"].startswith("kit_")
    assert token["scopes"] == ["read:messages", "write:messages"]

    result = await db_session.execute(
        select(AdminAuditLog).where(AdminAuditLog.target_id == uuid.UUID(bot["id"]))
    )
    actions = {e.action for e in result.scalars().all()}
    assert actions == {"bot.create", "bot.issue_token"}


async def test_create_token_rejects_unknown_scope(client, db_session):
    admin = await register_and_login(client, db_session, username="admin1")
    await _make_admin(db_session, admin["id"])
    bot = (await client.post("/api/admin/bots", json={"username": "helper-bot"})).json()

    resp = await client.post(
        f"/api/admin/bots/{bot['id']}/tokens", json={"scopes": ["delete:everything"]}
    )
    assert resp.status_code == 400


async def test_list_bots_includes_created_bot(client, db_session):
    admin = await register_and_login(client, db_session, username="admin1")
    await _make_admin(db_session, admin["id"])
    await client.post("/api/admin/bots", json={"username": "helper-bot"})

    resp = await client.get("/api/admin/bots")
    assert resp.status_code == 200
    usernames = {b["username"] for b in resp.json()}
    assert "helper-bot" in usernames


async def test_revoke_token_invalidates_it(client, db_session):
    admin = await register_and_login(client, db_session, username="admin1")
    await _make_admin(db_session, admin["id"])
    bot = (await client.post("/api/admin/bots", json={"username": "helper-bot"})).json()
    token = (
        await client.post(f"/api/admin/bots/{bot['id']}/tokens", json={"scopes": ["read:messages"]})
    ).json()

    revoke_resp = await client.delete(f"/api/admin/bots/tokens/{token['id']}")
    assert revoke_resp.status_code == 204

    # A revoked token should no longer authenticate anything.
    resp = await client.get(
        "/api/rooms", headers={"Authorization": f"Bearer {token['token']}"}
    )
    assert resp.status_code == 401


async def test_invalid_bearer_token_rejected(client):
    resp = await client.get("/api/rooms", headers={"Authorization": "Bearer kit_not-a-real-token"})
    assert resp.status_code == 401


def _unique(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _register_ws(ws_client, username: str) -> dict:
    from app.schemas.user import UserCreate
    from app.services.auth_service import register_user

    async def _seed():
        async with ws_client.session_factory() as session:
            await register_user(
                session,
                UserCreate(username=username, email=f"{username}@example.com", password="password123"),
            )

    ws_client.portal.call(_seed)
    resp = ws_client.post(
        "/api/auth/login", json={"username_or_email": username, "password": "password123"}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _make_admin_ws(ws_client, user_id: str) -> None:
    async def _promote():
        async with ws_client.session_factory() as session:
            user = await session.get(User, uuid.UUID(user_id))
            user.is_site_admin = True
            await session.commit()

    ws_client.portal.call(_promote)


def test_bot_ws_message_with_write_scope_succeeds(ws_client_factory):
    ws_client = ws_client_factory()
    admin = _register_ws(ws_client, _unique("admin"))
    _make_admin_ws(ws_client, admin["id"])

    room = ws_client.post("/api/rooms", json={"name": _unique("general")}).json()

    bot = ws_client.post("/api/admin/bots", json={"username": _unique("bot")}).json()
    token = ws_client.post(
        f"/api/admin/bots/{bot['id']}/tokens", json={"scopes": ["read:messages", "write:messages"]}
    ).json()["token"]

    # Bot joins the room via REST using its own bearer token -- exercises
    # bearer-token auth on the plain REST path, not just WS.
    join_resp = ws_client.post(
        f"/api/rooms/{room['id']}/join", headers={"Authorization": f"Bearer {token}"}
    )
    assert join_resp.status_code == 200

    with ws_client.websocket_connect(
        "/ws/chat", headers={"Authorization": f"Bearer {token}"}
    ) as ws:
        ws.send_json({"type": "join", "room_id": room["id"]})
        assert ws.receive_json()["type"] == "joined"
        ws.send_json({"type": "message", "room_id": room["id"], "content": "hello from bot"})
        message = ws.receive_json()
        assert message["type"] == "message"
        assert message["content"] == "hello from bot"
        assert message["username"] == bot["username"]


def test_bot_ws_message_without_write_scope_rejected(ws_client_factory):
    ws_client = ws_client_factory()
    admin = _register_ws(ws_client, _unique("admin"))
    _make_admin_ws(ws_client, admin["id"])

    room = ws_client.post("/api/rooms", json={"name": _unique("general")}).json()

    bot = ws_client.post("/api/admin/bots", json={"username": _unique("bot")}).json()
    token = ws_client.post(
        f"/api/admin/bots/{bot['id']}/tokens", json={"scopes": ["read:messages"]}
    ).json()["token"]

    ws_client.post(f"/api/rooms/{room['id']}/join", headers={"Authorization": f"Bearer {token}"})

    with ws_client.websocket_connect(
        "/ws/chat", headers={"Authorization": f"Bearer {token}"}
    ) as ws:
        ws.send_json({"type": "join", "room_id": room["id"]})
        assert ws.receive_json()["type"] == "joined"
        ws.send_json({"type": "message", "room_id": room["id"], "content": "hello"})
        resp = ws.receive_json()
        assert resp["type"] == "error"
        assert "write:messages" in resp["detail"]


def test_bot_rest_message_history_requires_read_scope(ws_client_factory):
    ws_client = ws_client_factory()
    admin = _register_ws(ws_client, _unique("admin"))
    _make_admin_ws(ws_client, admin["id"])

    room = ws_client.post("/api/rooms", json={"name": _unique("general")}).json()

    bot = ws_client.post("/api/admin/bots", json={"username": _unique("bot")}).json()
    write_only_token = ws_client.post(
        f"/api/admin/bots/{bot['id']}/tokens", json={"scopes": ["write:messages"]}
    ).json()["token"]
    read_token = ws_client.post(
        f"/api/admin/bots/{bot['id']}/tokens", json={"scopes": ["read:messages"]}
    ).json()["token"]

    ws_client.post(
        f"/api/rooms/{room['id']}/join", headers={"Authorization": f"Bearer {write_only_token}"}
    )

    no_scope_resp = ws_client.get(
        f"/api/rooms/{room['id']}/messages",
        headers={"Authorization": f"Bearer {write_only_token}"},
    )
    assert no_scope_resp.status_code == 403

    with_scope_resp = ws_client.get(
        f"/api/rooms/{room['id']}/messages", headers={"Authorization": f"Bearer {read_token}"}
    )
    assert with_scope_resp.status_code == 200
