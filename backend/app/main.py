import asyncio
import contextlib
import pathlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from redis.asyncio import Redis
from starlette.middleware.sessions import SessionMiddleware

from app.config import settings
from app.routers import (
    admin,
    auth,
    bots,
    custom_themes,
    health,
    push,
    rooms,
    signup,
    uploads,
    users,
    webhooks,
)
from app.ws.broadcaster import Broadcaster
from app.ws.chat import router as ws_router
from app.ws.connection_manager import ConnectionManager
from app.ws.global_presence import GlobalPresence
from app.ws.presence import Presence

# backend/app/main.py -> backend/ -> repo root -- matches both the local
# monorepo layout and the production layout (/srv/ds-chat/backend,
# /srv/ds-chat/frontend/dist), which is the same relative shape.
FRONTEND_DIST = pathlib.Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"


class ImmutableStaticFiles(StaticFiles):
    """Vite fingerprints these filenames by content hash, so once served a
    given path never changes -- safe to cache aggressively and skip
    revalidation entirely, unlike index.html/sw.js below."""

    async def get_response(self, path: str, scope) -> Response:
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response


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
    app = FastAPI(title="DS Chat", lifespan=lifespan)

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
    app.state.global_presence = GlobalPresence(app.state.redis)
    app.state.broadcaster = Broadcaster(app.state.redis, app.state.connection_manager)

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(signup.router)
    app.include_router(rooms.router)
    app.include_router(users.router)
    app.include_router(push.router)
    app.include_router(custom_themes.router)
    app.include_router(uploads.router)
    app.include_router(admin.router)
    app.include_router(bots.router)
    app.include_router(webhooks.router)
    app.include_router(ws_router)

    # Serves the built frontend so a single gunicorn port is enough for a
    # reverse proxy (e.g. Nginx Proxy Manager) to forward the whole domain
    # to -- no separate static-file host or per-path proxy routing needed
    # in front of it. Conditional on frontend/dist existing so local dev
    # (Vite's own dev server handles the frontend; frontend/dist is never
    # built there) is unaffected.
    if FRONTEND_DIST.is_dir():
        app.mount(
            "/assets", ImmutableStaticFiles(directory=FRONTEND_DIST / "assets"), name="frontend-assets"
        )

        # Must always be revalidated -- caching any of these is exactly how
        # a client ends up stuck on a stale app version after a deploy.
        # Vite's hashed /assets/ files (ImmutableStaticFiles above) are the
        # opposite case on purpose: their filename changes when their
        # content does, so there's nothing to revalidate.
        NO_CACHE_FILES = {"index.html", "sw.js", "registerSW.js", "manifest.webmanifest"}

        @app.get("/{full_path:path}", include_in_schema=False)
        async def serve_frontend(full_path: str) -> FileResponse:
            if full_path.startswith("api/") or full_path.startswith("ws/"):
                raise HTTPException(status_code=404)

            # .resolve() + is_relative_to() guards against path traversal
            # (e.g. full_path="../../etc/passwd") -- full_path comes
            # straight from the URL, and plain Path./ doesn't stop ".."
            # segments from escaping FRONTEND_DIST on its own.
            candidate = (FRONTEND_DIST / full_path).resolve()
            headers = {"Cache-Control": "no-cache"} if full_path in NO_CACHE_FILES else None
            if full_path and candidate.is_relative_to(FRONTEND_DIST) and candidate.is_file():
                return FileResponse(candidate, headers=headers)

            # Anything else is a client-side route (e.g. /rooms/<id>) --
            # fall back to the SPA shell, same as Nginx's `try_files $uri
            # /index.html` would have done.
            return FileResponse(FRONTEND_DIST / "index.html", headers={"Cache-Control": "no-cache"})

    return app


app = create_app()
