import asyncio
import contextlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from redis.asyncio import Redis
from starlette.middleware.sessions import SessionMiddleware

from app.config import settings
from app.routers import admin, auth, bots, health, invites, push, rooms, webhooks
from app.ws.broadcaster import RoomBroadcaster
from app.ws.chat import router as ws_router
from app.ws.connection_manager import ConnectionManager
from app.ws.presence import Presence


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # redis/presence/broadcaster are constructed in create_app(), not here --
    # Redis.from_url() is synchronous/lazy (no connection opens until the
    # first command), so app.state.presence/broadcaster are always present
    # even for callers that never trigger the ASGI lifespan (e.g. httpx's
    # ASGITransport, used by the plain REST test fixtures -- only
    # TestClient's websocket_connect-based tests actually run lifespan).
    # The background listener task genuinely needs a running event loop
    # though, so that part stays here.
    listener_task = asyncio.create_task(app.state.broadcaster.listen())

    yield

    listener_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await listener_task
    await app.state.redis.aclose()


def create_app() -> FastAPI:
    app = FastAPI(title="KeepItTalking", lifespan=lifespan)

    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.session_secret,
        same_site="lax",
        https_only=settings.session_https_only,
        max_age=settings.session_max_age_seconds,
    )

    app.state.connection_manager = ConnectionManager()
    app.state.redis = Redis.from_url(settings.redis_url, decode_responses=True)
    app.state.presence = Presence(app.state.redis)
    app.state.broadcaster = RoomBroadcaster(app.state.redis, app.state.connection_manager)

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(rooms.router)
    app.include_router(invites.router)
    app.include_router(push.router)
    app.include_router(admin.router)
    app.include_router(bots.router)
    app.include_router(webhooks.router)
    app.include_router(ws_router)

    return app


app = create_app()
