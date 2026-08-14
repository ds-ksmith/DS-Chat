from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware

from app.config import settings
from app.routers import auth, health, invites, rooms
from app.ws.chat import router as ws_router
from app.ws.connection_manager import ConnectionManager


def create_app() -> FastAPI:
    app = FastAPI(title="KeepItTalking")

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
    app.include_router(ws_router)

    return app


app = create_app()
