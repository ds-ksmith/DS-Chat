import io
import uuid

from PIL import Image

from app.models import User
from tests.conftest import register_and_login


def _unique(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _png_bytes(size: tuple[int, int] = (10, 10), color: tuple[int, int, int] = (255, 0, 0)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color=color).save(buf, format="PNG")
    return buf.getvalue()


async def _make_admin(db_session, user_id: str) -> None:
    user = await db_session.get(User, uuid.UUID(user_id))
    user.is_site_admin = True
    await db_session.commit()


async def test_upload_custom_emoji_succeeds(client, db_session):
    await register_and_login(client, db_session, username=_unique("alice"))
    resp = await client.post(
        "/api/custom-emoji",
        data={"shortcode": "party-parrot"},
        files={"file": ("parrot.png", _png_bytes(), "image/png")},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["shortcode"] == "party-parrot"
    assert "id" in body
    assert "created_at" in body


async def test_upload_normalizes_shortcode_case(client, db_session):
    await register_and_login(client, db_session, username=_unique("alice"))
    resp = await client.post(
        "/api/custom-emoji",
        data={"shortcode": "  PartyParrot  "},
        files={"file": ("parrot.png", _png_bytes(), "image/png")},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["shortcode"] == "partyparrot"


async def test_upload_rejects_invalid_shortcode(client, db_session):
    await register_and_login(client, db_session, username=_unique("alice"))
    resp = await client.post(
        "/api/custom-emoji",
        data={"shortcode": "a"},  # too short
        files={"file": ("x.png", _png_bytes(), "image/png")},
    )
    assert resp.status_code == 400


async def test_upload_rejects_duplicate_shortcode(client, db_session):
    await register_and_login(client, db_session, username=_unique("alice"))
    first = await client.post(
        "/api/custom-emoji",
        data={"shortcode": "dupe-test"},
        files={"file": ("a.png", _png_bytes(), "image/png")},
    )
    assert first.status_code == 201, first.text

    second = await client.post(
        "/api/custom-emoji",
        data={"shortcode": "dupe-test"},
        files={"file": ("b.png", _png_bytes(), "image/png")},
    )
    assert second.status_code == 409


async def test_upload_rejects_non_image(client, db_session):
    await register_and_login(client, db_session, username=_unique("alice"))
    resp = await client.post(
        "/api/custom-emoji",
        data={"shortcode": "not-an-image"},
        files={"file": ("x.txt", b"hello", "text/plain")},
    )
    assert resp.status_code == 400


async def test_upload_rejects_oversized(client, db_session):
    await register_and_login(client, db_session, username=_unique("alice"))
    oversized = b"0" * (9 * 1024 * 1024)
    resp = await client.post(
        "/api/custom-emoji",
        data={"shortcode": "too-big"},
        files={"file": ("huge.png", oversized, "image/png")},
    )
    assert resp.status_code == 413


async def test_list_custom_emoji(client, db_session):
    await register_and_login(client, db_session, username=_unique("alice"))
    await client.post(
        "/api/custom-emoji",
        data={"shortcode": _unique("listed")},
        files={"file": ("a.png", _png_bytes(), "image/png")},
    )
    resp = await client.get("/api/custom-emoji")
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


async def test_serve_custom_emoji_image_by_shortcode(client, db_session):
    await register_and_login(client, db_session, username=_unique("alice"))
    shortcode = _unique("served")
    upload = await client.post(
        "/api/custom-emoji",
        data={"shortcode": shortcode},
        files={"file": ("a.png", _png_bytes(), "image/png")},
    )
    assert upload.status_code == 201

    resp = await client.get(f"/api/custom-emoji/{shortcode}/image")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"


async def test_serve_custom_emoji_image_forces_revalidation(client, db_session):
    # A timed cache (the original `max-age=300`) meant a browser that had
    # already fetched a shortcode's image kept serving those bytes for up
    # to 5 minutes after a delete-and-reupload swapped in a different file
    # under the same URL -- confirmed live: re-adding an emoji under a
    # just-deleted shortcode showed the old image. `no-cache` forces
    # revalidation on every use instead (still cheap: FileResponse's own
    # ETag/Last-Modified make an actually-unchanged file a 304, not a full
    # re-transfer).
    await register_and_login(client, db_session, username=_unique("alice"))
    shortcode = _unique("revalidated")
    await client.post(
        "/api/custom-emoji",
        data={"shortcode": shortcode},
        files={"file": ("a.png", _png_bytes(), "image/png")},
    )
    resp = await client.get(f"/api/custom-emoji/{shortcode}/image")
    assert "no-cache" in resp.headers["cache-control"]
    assert "max-age" not in resp.headers["cache-control"]


async def test_reuploading_a_deleted_shortcode_serves_the_new_image(client, db_session):
    await register_and_login(client, db_session, username=_unique("alice"))
    shortcode = _unique("reused")
    first = await client.post(
        "/api/custom-emoji",
        data={"shortcode": shortcode},
        files={"file": ("red.png", _png_bytes(color=(255, 0, 0)), "image/png")},
    )
    assert first.status_code == 201
    await client.delete(f"/api/custom-emoji/{first.json()['id']}")

    second = await client.post(
        "/api/custom-emoji",
        data={"shortcode": shortcode},
        files={"file": ("blue.png", _png_bytes(color=(0, 0, 255)), "image/png")},
    )
    assert second.status_code == 201

    resp = await client.get(f"/api/custom-emoji/{shortcode}/image")
    served = Image.open(io.BytesIO(resp.content)).convert("RGB")
    assert served.getpixel((0, 0)) == (0, 0, 255)


async def test_serve_unknown_shortcode_404s(client, db_session):
    await register_and_login(client, db_session, username=_unique("alice"))
    resp = await client.get("/api/custom-emoji/no-such-emoji/image")
    assert resp.status_code == 404


async def test_uploader_can_delete_own_emoji(client, db_session):
    await register_and_login(client, db_session, username=_unique("alice"))
    upload = await client.post(
        "/api/custom-emoji",
        data={"shortcode": _unique("deleteme")},
        files={"file": ("a.png", _png_bytes(), "image/png")},
    )
    emoji_id = upload.json()["id"]

    resp = await client.delete(f"/api/custom-emoji/{emoji_id}")
    assert resp.status_code == 204

    listed = (await client.get("/api/custom-emoji")).json()
    assert emoji_id not in [e["id"] for e in listed]


async def test_non_uploader_non_admin_cannot_delete(client, app, db_session):
    from httpx import ASGITransport, AsyncClient

    await register_and_login(client, db_session, username=_unique("alice"))
    upload = await client.post(
        "/api/custom-emoji",
        data={"shortcode": _unique("guarded")},
        files={"file": ("a.png", _png_bytes(), "image/png")},
    )
    emoji_id = upload.json()["id"]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as bob_client:
        await register_and_login(bob_client, db_session, username=_unique("bob"))
        resp = await bob_client.delete(f"/api/custom-emoji/{emoji_id}")
        assert resp.status_code == 403

    listed = (await client.get("/api/custom-emoji")).json()
    assert emoji_id in [e["id"] for e in listed]


async def test_site_admin_can_delete_others_emoji(client, app, db_session):
    from httpx import ASGITransport, AsyncClient

    alice = await register_and_login(client, db_session, username=_unique("alice"))
    upload = await client.post(
        "/api/custom-emoji",
        data={"shortcode": _unique("admin-deletable")},
        files={"file": ("a.png", _png_bytes(), "image/png")},
    )
    emoji_id = upload.json()["id"]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as admin_client:
        admin = await register_and_login(admin_client, db_session, username=_unique("admin"))
        await _make_admin(db_session, admin["id"])
        resp = await admin_client.delete(f"/api/custom-emoji/{emoji_id}")
        assert resp.status_code == 204

    assert alice["id"]


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


def test_reaction_accepts_custom_emoji_shortcode_reference(ws_client_factory):
    instance = ws_client_factory()
    _register_ws(instance, _unique("alice"))
    room = instance.post("/api/rooms", json={"name": _unique("general")}).json()

    with instance.websocket_connect("/ws/chat") as ws:
        ws.send_json({"type": "join", "room_id": room["id"]})
        assert ws.receive_json()["type"] == "joined"
        ws.send_json({"type": "message", "room_id": room["id"], "content": "hello"})
        message = ws.receive_json()

        # A custom emoji reaction is stored as its literal `:shortcode:`
        # text (14 chars here) -- well past the old 8-char cap that only
        # ever needed to fit a raw unicode glyph.
        ws.send_json(
            {
                "type": "reaction",
                "room_id": room["id"],
                "message_id": message["id"],
                "emoji": ":party-parrot:",
            }
        )
        reaction_update = ws.receive_json()
        assert reaction_update["type"] == "reaction_update"
        assert reaction_update["reactions"][0]["emoji"] == ":party-parrot:"
