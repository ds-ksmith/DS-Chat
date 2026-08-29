import uuid
from datetime import datetime, timedelta, timezone

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Session

# #69: how stale last_seen_at has to be before a request bothers updating
# it. get_current_user resolves a session on *every* authenticated
# request (dozens per minute per active browser tab, between message
# polling, presence, etc.) -- writing+committing on every single one would
# turn a read into a write storm for no real benefit, since "active
# sessions" only needs last-seen accurate to within a few minutes, not to
# the second.
LAST_SEEN_THROTTLE = timedelta(minutes=5)


class SessionNotFoundError(Exception):
    pass


def get_client_ip(request_or_websocket) -> str | None:
    # X-Forwarded-For's first entry is the original client -- everything
    # after it was appended by intermediate proxies. Production runs
    # behind Nginx Proxy Manager (see backend/README.md's "Admin portal"
    # section preamble), which sets this; local dev has nothing in front
    # of the app, so this falls back to the direct peer address.
    forwarded = request_or_websocket.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    client = request_or_websocket.client
    return client.host if client else None


async def create_session(
    db: AsyncSession, user_id: uuid.UUID, ip_address: str | None, user_agent: str | None
) -> Session:
    session = Session(user_id=user_id, ip_address=ip_address, user_agent=user_agent)
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


async def start_session(request: Request, db: AsyncSession, user_id: uuid.UUID) -> Session:
    """Every "log this browser in" call site (login, reset-password
    completion, signup completion) needs the exact same three steps --
    read the request's IP/UA, create the row, stash its id in the signed
    cookie -- so this is the one place that combination lives."""
    session = await create_session(db, user_id, get_client_ip(request), request.headers.get("user-agent"))
    request.session["session_id"] = str(session.id)
    return session


async def resolve_session(db: AsyncSession, session_id: uuid.UUID) -> Session | None:
    """Returns the session iff it exists and hasn't been revoked -- the
    single choke point get_current_user and the WS handshake both go
    through, so revoking a session (this endpoint or another device's
    "sign out") takes effect on that session's very next request rather
    than only once its signed cookie happens to expire."""
    session = await db.get(Session, session_id)
    if session is None or session.revoked_at is not None:
        return None

    now = datetime.now(timezone.utc)
    if now - session.last_seen_at > LAST_SEEN_THROTTLE:
        session.last_seen_at = now
        await db.commit()
    return session


async def list_sessions(db: AsyncSession, user_id: uuid.UUID) -> list[Session]:
    result = await db.execute(
        select(Session)
        .where(Session.user_id == user_id, Session.revoked_at.is_(None))
        .order_by(Session.last_seen_at.desc())
    )
    return list(result.scalars().all())


async def revoke_session(db: AsyncSession, user_id: uuid.UUID, session_id: uuid.UUID) -> None:
    session = await db.get(Session, session_id)
    if session is None or session.user_id != user_id or session.revoked_at is not None:
        raise SessionNotFoundError()
    session.revoked_at = datetime.now(timezone.utc)
    await db.commit()


async def revoke_session_unchecked(db: AsyncSession, session_id: uuid.UUID) -> None:
    """Logout's own path -- no ownership check needed (a session can only
    ever log itself out) and silently does nothing for a session that's
    missing or already revoked, since "sign this browser out" should
    never itself fail."""
    session = await db.get(Session, session_id)
    if session is None or session.revoked_at is not None:
        return
    session.revoked_at = datetime.now(timezone.utc)
    await db.commit()
