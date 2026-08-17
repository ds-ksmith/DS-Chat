import uuid

from tests.conftest import register_and_login


def _unique(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _sample_colors(**overrides) -> dict:
    colors = {
        "void": "#07080f",
        "void_2": "#0b0c1a",
        "surface": "#101030",
        "surface_2": "#181848",
        "border": "#242478",
        "text": "#fce4fc",
        "muted": "#c0ccd8",
        "accent": "#60d8fc",
        "accent_2": "#6c60fc",
        "accent_3": "#7848fc",
        "highlight": "#f060fc",
        "danger": "#fc6060",
        "color_scheme": "dark",
    }
    colors.update(overrides)
    return colors


async def test_create_and_list_custom_themes(client, db_session):
    await register_and_login(client, db_session, username=_unique("alice"))

    resp = await client.post(
        "/api/custom-themes", json={"name": "Sunset Vibes", "colors": _sample_colors()}
    )
    assert resp.status_code == 201, resp.text
    created = resp.json()
    assert created["name"] == "Sunset Vibes"
    assert created["colors"] == _sample_colors()

    resp = await client.get("/api/custom-themes")
    assert resp.status_code == 200
    themes = resp.json()
    assert len(themes) == 1
    assert themes[0]["id"] == created["id"]


async def test_create_rejects_bad_hex(client, db_session):
    await register_and_login(client, db_session, username=_unique("alice"))

    resp = await client.post(
        "/api/custom-themes",
        json={"name": "Bad", "colors": _sample_colors(accent="not-a-color")},
    )
    assert resp.status_code == 422


async def test_create_rejects_missing_field(client, db_session):
    await register_and_login(client, db_session, username=_unique("alice"))

    colors = _sample_colors()
    del colors["danger"]
    resp = await client.post("/api/custom-themes", json={"name": "Incomplete", "colors": colors})
    assert resp.status_code == 422


async def test_create_rejects_invalid_color_scheme(client, db_session):
    await register_and_login(client, db_session, username=_unique("alice"))

    resp = await client.post(
        "/api/custom-themes",
        json={"name": "Bad scheme", "colors": _sample_colors(color_scheme="sepia")},
    )
    assert resp.status_code == 422


async def test_activate_sets_theme_and_resolves_colors(client, db_session):
    await register_and_login(client, db_session, username=_unique("alice"))
    created = (
        await client.post("/api/custom-themes", json={"name": "Mine", "colors": _sample_colors()})
    ).json()

    resp = await client.post(f"/api/custom-themes/{created['id']}/activate")
    assert resp.status_code == 200, resp.text
    assert resp.json()["theme"] == "custom"
    assert resp.json()["active_custom_theme"]["id"] == created["id"]
    assert resp.json()["active_custom_theme"]["colors"] == _sample_colors()

    me = await client.get("/api/auth/me")
    assert me.json()["active_custom_theme"]["name"] == "Mine"


async def test_switching_to_preset_and_back_preserves_saved_theme(client, db_session):
    # Switching to a preset and back must not lose a saved custom theme --
    # there's no reason picking "Dark" for a moment should force redoing all
    # 12 color picks if you switch back later.
    await register_and_login(client, db_session, username=_unique("alice"))
    created = (
        await client.post("/api/custom-themes", json={"name": "Mine", "colors": _sample_colors()})
    ).json()
    await client.post(f"/api/custom-themes/{created['id']}/activate")

    resp = await client.patch("/api/auth/me", json={"theme": "dark"})
    assert resp.status_code == 200
    assert resp.json()["theme"] == "dark"
    assert resp.json()["active_custom_theme"] is None

    resp = await client.post(f"/api/custom-themes/{created['id']}/activate")
    assert resp.status_code == 200
    assert resp.json()["active_custom_theme"]["colors"] == _sample_colors()


async def test_update_renames_and_recolors(client, db_session):
    await register_and_login(client, db_session, username=_unique("alice"))
    created = (
        await client.post("/api/custom-themes", json={"name": "Old name", "colors": _sample_colors()})
    ).json()

    resp = await client.patch(
        f"/api/custom-themes/{created['id']}", json={"name": "New name"}
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "New name"
    assert resp.json()["colors"] == _sample_colors()

    resp = await client.patch(
        f"/api/custom-themes/{created['id']}", json={"colors": _sample_colors(accent="#ff3366")}
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "New name"
    assert resp.json()["colors"]["accent"] == "#ff3366"


async def test_delete_non_active_theme_leaves_active_theme_untouched(client, db_session):
    await register_and_login(client, db_session, username=_unique("alice"))
    active = (
        await client.post("/api/custom-themes", json={"name": "Active", "colors": _sample_colors()})
    ).json()
    other = (
        await client.post(
            "/api/custom-themes", json={"name": "Other", "colors": _sample_colors(accent="#ff3366")}
        )
    ).json()
    await client.post(f"/api/custom-themes/{active['id']}/activate")

    resp = await client.delete(f"/api/custom-themes/{other['id']}")
    assert resp.status_code == 204

    me = (await client.get("/api/auth/me")).json()
    assert me["theme"] == "custom"
    assert me["active_custom_theme"]["id"] == active["id"]


async def test_delete_active_theme_falls_back_to_preset(client, db_session):
    await register_and_login(client, db_session, username=_unique("alice"))
    created = (
        await client.post("/api/custom-themes", json={"name": "Mine", "colors": _sample_colors()})
    ).json()
    await client.post(f"/api/custom-themes/{created['id']}/activate")

    resp = await client.delete(f"/api/custom-themes/{created['id']}")
    assert resp.status_code == 204

    me = (await client.get("/api/auth/me")).json()
    assert me["theme"] == "dark"
    assert me["active_custom_theme"] is None
    assert (await client.get("/api/custom-themes")).json() == []


async def test_ownership_enforced_across_users(client, db_session):
    await register_and_login(client, db_session, username=_unique("alice"))
    created = (
        await client.post("/api/custom-themes", json={"name": "Alice's", "colors": _sample_colors()})
    ).json()

    await register_and_login(client, db_session, username=_unique("bob"))

    resp = await client.patch(f"/api/custom-themes/{created['id']}", json={"name": "Hijacked"})
    assert resp.status_code == 404

    resp = await client.delete(f"/api/custom-themes/{created['id']}")
    assert resp.status_code == 404

    resp = await client.post(f"/api/custom-themes/{created['id']}/activate")
    assert resp.status_code == 404

    # Bob's own list is untouched by alice's theme.
    assert (await client.get("/api/custom-themes")).json() == []


async def test_custom_theme_limit(client, db_session, monkeypatch):
    monkeypatch.setattr(
        "app.services.custom_theme_service.MAX_CUSTOM_THEMES_PER_USER", 2
    )
    await register_and_login(client, db_session, username=_unique("alice"))

    for i in range(2):
        resp = await client.post(
            "/api/custom-themes", json={"name": f"Theme {i}", "colors": _sample_colors()}
        )
        assert resp.status_code == 201, resp.text

    resp = await client.post(
        "/api/custom-themes", json={"name": "One too many", "colors": _sample_colors()}
    )
    assert resp.status_code == 400
