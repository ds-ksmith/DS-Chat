import io
import uuid

from PIL import Image

from app.storage import UPLOADS_DIR
from tests.conftest import register_and_login


def _unique(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _png_bytes(size: tuple[int, int] = (10, 10)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color=(255, 0, 0)).save(buf, format="PNG")
    return buf.getvalue()


async def test_update_display_name_persists(client, db_session):
    await register_and_login(client, db_session, username=_unique("alice"))

    resp = await client.patch("/api/auth/me", json={"display_name": "Alice A."})
    assert resp.status_code == 200, resp.text
    assert resp.json()["display_name"] == "Alice A."

    me = await client.get("/api/auth/me")
    assert me.json()["display_name"] == "Alice A."


async def test_empty_display_name_clears_it(client, db_session):
    await register_and_login(client, db_session, username=_unique("alice"))
    await client.patch("/api/auth/me", json={"display_name": "Alice A."})

    resp = await client.patch("/api/auth/me", json={"display_name": ""})
    assert resp.status_code == 200
    assert resp.json()["display_name"] is None


async def test_whitespace_display_name_clears_it(client, db_session):
    await register_and_login(client, db_session, username=_unique("alice"))
    await client.patch("/api/auth/me", json={"display_name": "Alice A."})

    resp = await client.patch("/api/auth/me", json={"display_name": "   "})
    assert resp.status_code == 200
    assert resp.json()["display_name"] is None


async def test_display_name_too_long_rejected(client, db_session):
    await register_and_login(client, db_session, username=_unique("alice"))

    resp = await client.patch("/api/auth/me", json={"display_name": "x" * 51})
    assert resp.status_code == 422


async def test_update_theme_persists(client, db_session):
    await register_and_login(client, db_session, username=_unique("alice"))

    resp = await client.patch("/api/auth/me", json={"theme": "midnight"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["theme"] == "midnight"

    me = await client.get("/api/auth/me")
    assert me.json()["theme"] == "midnight"


async def test_invalid_theme_rejected(client, db_session):
    await register_and_login(client, db_session, username=_unique("alice"))

    resp = await client.patch("/api/auth/me", json={"theme": "not-a-real-theme"})
    assert resp.status_code == 422


async def test_updating_theme_does_not_clobber_display_name(client, db_session):
    await register_and_login(client, db_session, username=_unique("alice"))
    await client.patch("/api/auth/me", json={"display_name": "Alice A."})

    resp = await client.patch("/api/auth/me", json={"theme": "light"})
    assert resp.status_code == 200
    assert resp.json()["display_name"] == "Alice A."
    assert resp.json()["theme"] == "light"


async def test_updating_display_name_does_not_clobber_theme(client, db_session):
    await register_and_login(client, db_session, username=_unique("alice"))
    await client.patch("/api/auth/me", json={"theme": "sunset"})

    resp = await client.patch("/api/auth/me", json={"display_name": "Alice A."})
    assert resp.status_code == 200
    assert resp.json()["theme"] == "sunset"
    assert resp.json()["display_name"] == "Alice A."


async def test_avatar_upload_succeeds_and_persists(client, db_session):
    await register_and_login(client, db_session, username=_unique("alice"))

    resp = await client.post(
        "/api/auth/me/avatar", files={"file": ("test.png", _png_bytes(), "image/png")}
    )
    assert resp.status_code == 200, resp.text
    filename = resp.json()["avatar_filename"]
    assert filename

    me = await client.get("/api/auth/me")
    assert me.json()["avatar_filename"] == filename


async def test_avatar_reupload_deletes_old_file(client, db_session):
    await register_and_login(client, db_session, username=_unique("alice"))

    first = await client.post(
        "/api/auth/me/avatar", files={"file": ("first.png", _png_bytes(), "image/png")}
    )
    first_filename = first.json()["avatar_filename"]
    assert (UPLOADS_DIR / first_filename).exists()

    second = await client.post(
        "/api/auth/me/avatar", files={"file": ("second.png", _png_bytes((20, 20)), "image/png")}
    )
    second_filename = second.json()["avatar_filename"]
    assert second_filename != first_filename
    assert not (UPLOADS_DIR / first_filename).exists()
    assert (UPLOADS_DIR / second_filename).exists()


async def test_avatar_oversized_rejected(client, db_session):
    await register_and_login(client, db_session, username=_unique("alice"))

    oversized = b"0" * (9 * 1024 * 1024)
    resp = await client.post(
        "/api/auth/me/avatar", files={"file": ("huge.png", oversized, "image/png")}
    )
    assert resp.status_code == 413


async def test_avatar_non_image_rejected(client, db_session):
    await register_and_login(client, db_session, username=_unique("alice"))

    resp = await client.post(
        "/api/auth/me/avatar", files={"file": ("fake.png", b"not an image", "image/png")}
    )
    assert resp.status_code == 400


async def test_avatar_visible_without_shared_room(client, db_session):
    alice = await register_and_login(client, db_session, username=_unique("alice"))
    await client.post(
        "/api/auth/me/avatar", files={"file": ("test.png", _png_bytes(), "image/png")}
    )

    # bob shares no room with alice at all -- unlike message images (room-
    # gated), avatar visibility matches username visibility: any
    # authenticated user can see it.
    await register_and_login(client, db_session, username=_unique("bob"))
    resp = await client.get(f"/api/users/{alice['id']}/avatar")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"


async def test_remove_avatar_clears_and_404s(client, db_session):
    alice = await register_and_login(client, db_session, username=_unique("alice"))
    await client.post(
        "/api/auth/me/avatar", files={"file": ("test.png", _png_bytes(), "image/png")}
    )

    resp = await client.delete("/api/auth/me/avatar")
    assert resp.status_code == 200
    assert resp.json()["avatar_filename"] is None

    avatar_resp = await client.get(f"/api/users/{alice['id']}/avatar")
    assert avatar_resp.status_code == 404


async def test_room_members_include_avatar_filename(client, db_session):
    await register_and_login(client, db_session, username=_unique("alice"))
    upload = await client.post(
        "/api/auth/me/avatar", files={"file": ("test.png", _png_bytes(), "image/png")}
    )
    avatar_filename = upload.json()["avatar_filename"]

    room = (await client.post("/api/rooms", json={"name": _unique("general")})).json()
    members = (await client.get(f"/api/rooms/{room['id']}/members")).json()
    assert members[0]["avatar_filename"] == avatar_filename
