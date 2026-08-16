import uuid

from sqlalchemy import select

from app.models import UploadSettings, User
from tests.conftest import register_and_login


async def _get_settings_row(db_session) -> UploadSettings:
    result = await db_session.execute(select(UploadSettings))
    return result.scalar_one()


async def _make_admin(db_session, user_id: str) -> None:
    user = await db_session.get(User, uuid.UUID(user_id))
    user.is_site_admin = True
    await db_session.commit()


async def test_upload_settings_require_admin(client, db_session):
    await register_and_login(client, db_session, username="alice")
    resp = await client.get("/api/admin/settings/uploads")
    assert resp.status_code == 403

    resp = await client.put("/api/admin/settings/uploads", json={"max_upload_bytes": 1024 * 1024})
    assert resp.status_code == 403


async def test_upload_settings_get_defaults_to_8mb(client, db_session):
    admin = await register_and_login(client, db_session, username="admin1")
    await _make_admin(db_session, admin["id"])

    resp = await client.get("/api/admin/settings/uploads")
    assert resp.status_code == 200
    assert resp.json()["max_upload_bytes"] == 8 * 1024 * 1024


async def test_upload_settings_update(client, db_session):
    admin = await register_and_login(client, db_session, username="admin1")
    await _make_admin(db_session, admin["id"])

    resp = await client.put("/api/admin/settings/uploads", json={"max_upload_bytes": 20 * 1024 * 1024})
    assert resp.status_code == 200
    assert resp.json()["max_upload_bytes"] == 20 * 1024 * 1024

    resp = await client.get("/api/admin/settings/uploads")
    assert resp.json()["max_upload_bytes"] == 20 * 1024 * 1024

    row = await _get_settings_row(db_session)
    assert row.max_upload_bytes == 20 * 1024 * 1024


async def test_upload_settings_rejects_out_of_range(client, db_session):
    admin = await register_and_login(client, db_session, username="admin1")
    await _make_admin(db_session, admin["id"])

    resp = await client.put("/api/admin/settings/uploads", json={"max_upload_bytes": 0})
    assert resp.status_code == 422

    resp = await client.put(
        "/api/admin/settings/uploads", json={"max_upload_bytes": 1000 * 1024 * 1024}
    )
    assert resp.status_code == 422


async def test_upload_limit_endpoint_accessible_to_any_authenticated_user(client, db_session):
    admin = await register_and_login(client, db_session, username="admin1")
    await _make_admin(db_session, admin["id"])
    await client.put("/api/admin/settings/uploads", json={"max_upload_bytes": 5 * 1024 * 1024})

    await register_and_login(client, db_session, username="regular")
    resp = await client.get("/api/uploads/limit")
    assert resp.status_code == 200
    assert resp.json()["max_upload_bytes"] == 5 * 1024 * 1024


async def test_lowering_limit_enforced_on_file_upload(client, db_session):
    admin = await register_and_login(client, db_session, username="admin1")
    await _make_admin(db_session, admin["id"])
    await client.put("/api/admin/settings/uploads", json={"max_upload_bytes": 1024 * 1024})

    room = (await client.post("/api/rooms", json={"name": "general"})).json()

    resp = await client.post(
        f"/api/rooms/{room['id']}/files",
        files={"file": ("big.bin", b"0" * (2 * 1024 * 1024), "application/octet-stream")},
    )
    assert resp.status_code == 413
    assert "1 MB" in resp.json()["detail"]

    resp = await client.post(
        f"/api/rooms/{room['id']}/files",
        files={"file": ("small.bin", b"0" * (512 * 1024), "application/octet-stream")},
    )
    assert resp.status_code == 201


async def test_raising_limit_allows_larger_image_upload(client, db_session):
    admin = await register_and_login(client, db_session, username="admin1")
    await _make_admin(db_session, admin["id"])
    await client.put("/api/admin/settings/uploads", json={"max_upload_bytes": 20 * 1024 * 1024})

    room = (await client.post("/api/rooms", json={"name": "general"})).json()

    # 9MB would be rejected under the old hardcoded 8MB cap.
    oversized_for_old_cap = b"0" * (9 * 1024 * 1024)
    resp = await client.post(
        f"/api/rooms/{room['id']}/images",
        files={"file": ("big.bin", oversized_for_old_cap, "image/png")},
    )
    # Not a valid PNG, but it must get past the size check to prove the
    # raised limit took effect -- 400 (invalid image), not 413.
    assert resp.status_code == 400
