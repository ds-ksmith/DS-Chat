import asyncio
import contextlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from redis.asyncio import Redis
from starlette.middleware.sessions import SessionMiddleware

from app.config import settings
from app.routers import auth, health, invites, push, rooms
from app.ws.broadcaster import RoomBroadcaster
from app.ws.chat import router as ws_router
from app.ws.connection_manager import ConnectionManager
from app.ws.presence import Presence


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    app.state.presence = Presence(redis)
    broadcaster = RoomBroadcaster(redis, app.state.connection_manager)
    app.state.broadcaster = broadcaster
    listener_task = asyncio.create_task(broadcaster.listen())

    yield

    listener_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await listener_task
    await redis.aclose()


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

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(rooms.router)
    app.include_router(invites.router)
    app.include_router(push.router)
    app.include_router(ws_router)

    return app


app = create_app()
