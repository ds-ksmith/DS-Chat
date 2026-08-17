import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.cli import _create_user, _prompt_password
from app.database import async_session_factory
from app.database import engine as _cli_engine
from app.models import User


def _unique(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


@pytest_asyncio.fixture(autouse=True)
async def _dispose_cli_engine_between_tests():
    # _create_user (like the real CLI) uses app.database's module-level
    # engine directly, not the db_session fixture's own per-test engine --
    # pytest-asyncio gives each test function a fresh event loop by
    # default, and a pooled connection opened on a since-closed loop
    # produces asyncpg "another operation is in progress" errors if reused
    # by a later test. Disposing after every test forces a fresh connection
    # next time instead of reusing a stale one.
    yield
    await _cli_engine.dispose()


async def _get_user(username: str) -> User | None:
    async with async_session_factory() as session:
        result = await session.execute(select(User).where(User.username == username))
        return result.scalar_one_or_none()


def test_prompt_password_matches_on_first_try(monkeypatch):
    responses = iter(["correct-horse", "correct-horse"])
    monkeypatch.setattr("getpass.getpass", lambda prompt="": next(responses))

    assert _prompt_password() == "correct-horse"


def test_prompt_password_retries_on_mismatch(monkeypatch, capsys):
    responses = iter(["typo-password", "correct-password", "correct-password", "correct-password"])
    monkeypatch.setattr("getpass.getpass", lambda prompt="": next(responses))

    assert _prompt_password() == "correct-password"
    assert "didn't match" in capsys.readouterr().out


async def test_create_user_with_explicit_password_succeeds():
    username = _unique("alice")
    await _create_user(username, f"{username}@example.com", "password123", False)

    user = await _get_user(username)
    assert user is not None
    assert user.is_site_admin is False


async def test_create_user_via_prompted_password(monkeypatch):
    responses = iter(["prompted-pass", "prompted-pass"])
    monkeypatch.setattr("getpass.getpass", lambda prompt="": next(responses))

    username = _unique("bob")
    password = _prompt_password()
    await _create_user(username, f"{username}@example.com", password, True)

    user = await _get_user(username)
    assert user is not None
    assert user.is_site_admin is True


async def test_create_user_rejects_short_password():
    username = _unique("shortpw")
    with pytest.raises(SystemExit):
        await _create_user(username, f"{username}@example.com", "short", False)

    assert await _get_user(username) is None
