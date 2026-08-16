import contextlib
import os
from pathlib import Path

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://chatapp:chatapp@localhost:5432/ds_chat_test"
)
os.environ.setdefault("SESSION_SECRET", "test-secret")
os.environ.setdefault("SESSION_HTTPS_ONLY", "false")
# DB index 15 keeps test presence/pub-sub state separate from whatever a
# developer's local Redis is doing on db 0.
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.database import get_db
from app.main import create_app
from app.schemas.user import UserCreate
from app.services.auth_service import register_user

BACKEND_DIR = Path(__file__).resolve().parent.parent
TEST_DATABASE_URL = os.environ["DATABASE_URL"]


@pytest.fixture(scope="session", autouse=True)
def apply_migrations():
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    command.upgrade(config, "head")
    yield


@pytest_asyncio.fixture
async def db_session():
    # Function-scoped (not session-scoped): asyncpg connections are bound to
    # the event loop they were created on, and pytest-asyncio gives each test
    # function its own loop by default. A session-scoped engine here would be
    # reused across loops and fail with asyncpg "another operation is in
    # progress" errors.
    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.connect() as conn:
        await conn.begin()
        # expire_on_commit=False matches app/database.py's production session
        # factory -- without it, objects loaded earlier in a request (e.g.
        # current_user) go stale after any service-layer commit and touching
        # them raises MissingGreenlet on the next sync attribute access.
        session = AsyncSession(
            bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False
        )
        yield session
        await session.close()
        await conn.rollback()
    await engine.dispose()


@pytest.fixture
def app(db_session):
    application = create_app()

    async def _get_db():
        yield db_session

    application.dependency_overrides[get_db] = _get_db
    yield application
    application.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def ws_client_factory():
    # Starlette's TestClient (needed for websocket_connect, which httpx's
    # async client doesn't support) runs the ASGI app on a background thread
    # with its own event loop via anyio's BlockingPortal. asyncpg connections
    # are bound to the loop they're opened on, so each app built here gets
    # its own engine (no connections opened yet) rather than reusing the
    # `db_session`/`app` fixtures' engine, which belongs to pytest's loop.
    # No per-test rollback here (see test_ws_chat.py for the unique-name
    # convention that keeps tests independent without it).
    #
    # poolclass=NullPool: with pooling, a WS test that does more than one
    # DB round trip per message (e.g. the offline-push lookup) can hit a
    # race where the pooled connection returned by the WS handler's session
    # close hasn't finished being checked back in before the test's next
    # (synchronous, same-portal) REST call checks a connection back out --
    # surfaces as "connection is closed". A fresh connection per session
    # sidesteps it; fine for tests, not something prod needs (prod isn't
    # juggling a background portal thread against the main test thread).
    #
    # A factory (not a single client) so tests can spin up more than one
    # independent app instance -- sharing the same test Postgres and Redis,
    # like separate app-server processes behind Nginx would -- to exercise
    # cross-instance broadcast/presence (see test_broadcast.py). Each
    # TestClient is entered via an ExitStack so its lifespan (which opens
    # the Redis connection/pubsub listener) starts immediately and all of
    # them get torn down together at fixture teardown.
    stack = contextlib.ExitStack()

    def _make() -> TestClient:
        application = create_app()
        test_engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
        test_session_factory = async_sessionmaker(test_engine, expire_on_commit=False)

        async def _get_db():
            async with test_session_factory() as session:
                yield session

        application.dependency_overrides[get_db] = _get_db

        tc = stack.enter_context(TestClient(application))
        tc.session_factory = test_session_factory  # type: ignore[attr-defined]
        return tc

    yield _make
    stack.close()


@pytest.fixture
def ws_client(ws_client_factory):
    return ws_client_factory()


async def register_and_login(
    client: AsyncClient,
    db_session: AsyncSession,
    username: str = "alice",
    password: str = "password123",
):
    # No public register endpoint (invite-only site) -- tests seed the
    # account the same way an operator would via `python -m app.cli
    # create-user`, by calling the service function directly, then log in
    # through the real endpoint to get a session cookie on `client`.
    data = UserCreate(username=username, email=f"{username}@example.com", password=password)
    await register_user(db_session, data)

    return await login_as(client, username, password)


async def login_as(client: AsyncClient, username: str, password: str = "password123"):
    # Switch the shared `client`'s session cookie to an already-created user,
    # without trying to register them again.
    resp = await client.post(
        "/api/auth/login",
        json={"username_or_email": username, "password": password},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()
