# KeepItTalking backend (Phase 1 + 2 + 4 + 5)

FastAPI + SQLAlchemy 2.0 (async) + PostgreSQL + Redis. Implements auth, room
CRUD (open and private), room roles (owner/admin/member) and invites, a
WebSocket chat endpoint that fans out across multiple app-server instances
via Redis pub/sub, and Web Push notifications for offline room members. See
`../ARCHITECTURE.md` for the full system design and the phased build plan.

This is an **invite-only site**: there is no public registration endpoint.
Accounts are created by an operator on the app server — see step 4 below.

## Local dev setup

### 1. Postgres

Any local Postgres 14+ works. The quickest option is a container:

```bash
docker run -d --name chatapp-postgres \
  -e POSTGRES_USER=chatapp -e POSTGRES_PASSWORD=chatapp -e POSTGRES_DB=chatapp \
  -p 5432:5432 postgres:16-alpine
```

Then create the test database (used by the test suite, kept separate from dev data):

```bash
docker exec chatapp-postgres psql -U chatapp -d chatapp -c "CREATE DATABASE chatapp_test;"
```

(Docker here is purely a local-dev convenience for standing up Postgres quickly —
the actual deployment target has no containers at all, see `ARCHITECTURE.md` §9.)

### 2. Redis

Used for cross-instance WebSocket fan-out and presence (see the section
below). Required — there's no in-memory fallback.

```bash
docker run -d --name chatapp-redis -p 6379:6379 redis:7-alpine
```

### 3. Python environment

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
cp .env.example .env
# edit .env: set SESSION_SECRET to a long random string, e.g.
#   python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

### 4. Migrations

```bash
.venv/bin/alembic upgrade head
```

### 5. Create a user

There's no public sign-up. Create accounts directly with the CLI (add
`--admin` to grant `is_site_admin`, useful ahead of the phase-6 admin portal):

```bash
.venv/bin/python -m app.cli create-user alice alice@example.com "some-password"
```

### 6. (Optional) Set up push notifications

Push works without any setup — `VAPID_PUBLIC_KEY`/`VAPID_PRIVATE_KEY` are
unset by default and push delivery is silently skipped. To enable it:

```bash
.venv/bin/python -m app.cli generate-vapid-keys
# paste the three printed lines into backend/.env
```

### 7. Run the dev server

```bash
.venv/bin/uvicorn app.main:app --reload
```

API docs: http://localhost:8000/docs. WebSocket chat endpoint: `ws://localhost:8000/ws/chat`.

To try horizontal scaling locally, run a second instance on another port
against the same Postgres + Redis (`.venv/bin/uvicorn app.main:app --port 8001`)
— a message sent through one instance's WebSocket is delivered to clients
connected to the other, purely via Redis.

### 8. Run tests

Tests run against a real Postgres database (`chatapp_test` by default — native
`ENUM`/`UUID` types aren't faithfully reproduced by SQLite) and a real Redis
(db 15 by default, kept separate from dev use of db 0), with each test
wrapped in a transaction that's rolled back afterward:

```bash
DATABASE_URL=postgresql+asyncpg://chatapp:chatapp@localhost:5432/chatapp_test .venv/bin/pytest
```

## Layout

```
app/
  main.py            create_app(), session middleware, router/WS mounting
  config.py           environment-driven settings (pydantic-settings)
  database.py          async engine/session, get_db() dependency
  dependencies.py       get_current_user, require_room_member, require_room_role
  security.py            argon2 password hashing
  cli.py                  `python -m app.cli create-user` / `generate-vapid-keys`
  models/                 SQLAlchemy models (users, rooms, room_memberships,
                             messages, room_invites, push_subscriptions)
  schemas/                 Pydantic request/response models
  routers/                  auth, rooms, invites, push, health
  services/                  business logic called by routers
  ws/                        connection_manager (local sockets), presence +
                               broadcaster (Redis), /ws/chat handler
alembic/                      migrations
tests/                         pytest + httpx/TestClient tests
```

## Cross-instance broadcast (Phase 5)

The WebSocket layer is split into three pieces so that running one app
instance and running many behave identically:
- `app/ws/connection_manager.py` — purely local: which sockets on *this*
  process are in which room, used only to actually `send_json` to them.
- `app/ws/broadcaster.py` (`RoomBroadcaster`) — on a chat message,
  `publish()`s it to a Redis channel scoped to the room (`room:{id}`).
  Every app instance, including the publisher, runs a single background
  `listen()` task (started in `app/main.py`'s lifespan) pattern-subscribed
  to `room:*`; each message it receives is handed to its own local
  `ConnectionManager.broadcast()`. One instance just talks to itself
  through Redis, so there's no separate single-instance code path.
- `app/ws/presence.py` (`Presence`) — a Redis hash per room
  (`presence:{room_id}`, field = user ID, value = connection refcount) is
  the cross-instance answer to "is this member connected *anywhere* right
  now," which is what the Phase 4 offline-push check uses instead of the
  local `ConnectionManager`. Refcounted so a user connected from two tabs
  (or two instances) isn't marked offline until every connection closes.

Known limitation: `Presence` has no heartbeat/TTL, so a hard process crash
(not a clean disconnect) leaks that connection's increment forever — same
category of simplification as the "no server-side session revocation" note
below.

## Push notifications (Phase 4)

`POST /api/push/subscribe` (upserts by `endpoint`) / `DELETE /api/push/subscribe`
manage a user's `push_subscriptions` rows; `GET /api/push/vapid-public-key` gives
the frontend the key it needs for `PushManager.subscribe()`. On every chat
message, `app/ws/chat.py` computes `room members - Presence.
connected_user_ids(room_id)` (who's actually connected to *that room* right
now, across every app instance — see Phase 5 below) and sends each offline
member a push via `pywebpush`, awaited inline against the same
request-scoped session rather than fired as a background task — the
broadcast to online members already happened by that point, so nothing
online-facing is delayed, and it sidesteps `asyncio.create_task()`s outliving
the session/event loop they were created on. An expired/invalid subscription
(pywebpush 404/410) is deleted automatically.

## Room roles and invites (Phase 2)

Rooms can be `open` (anyone can join via `POST /api/rooms/{id}/join`) or
`private` (`is_private: true` at creation — joinable only via invite). Room
roles are `owner` > `admin` > `member`:
- **member**: post messages, leave the room
- **admin**: edit room settings, create/list/revoke invites, remove plain members
- **owner**: everything admin can, plus delete the room, remove admins, change
  member roles, and transfer ownership

Invite flow: an admin+ calls `POST /api/rooms/{id}/invites` with an existing
`target_username`; the invited user sees it via `GET /api/invites/mine` and
calls `POST /api/invites/{id}/accept` (or `/decline`). `GET /api/rooms/mine`
lists every room (open + private) the current user belongs to, alongside
their role.

## Notes / scope decisions

- Invite-only site registration: no `POST /api/auth/register`. Accounts are
  provisioned with `python -m app.cli create-user` (see step 4 above). This is
  separate from *room* invites above — site accounts vs. room membership.
- Room invites are by **username only** — `room_invites.target_email` exists
  in the schema (per `ARCHITECTURE.md`) but is unused, since there's no
  email-delivery mechanism anywhere in the stack yet.
- Sessions are signed cookies (Starlette `SessionMiddleware`), not a server-side
  session table — see `ARCHITECTURE.md`'s rationale (simplest way to carry auth
  through a WebSocket handshake). This means there's currently no way to force-
  revoke a session server-side; that needs a real session table later.
- No CSRF token yet — `SameSite=Lax` cookies plus a same-origin frontend dev
  proxy (see `../frontend/vite.config.ts`) is the accepted phase-1 mitigation.
- Deleting a room explicitly deletes its messages/memberships/invites first
  (`room_service.delete_room`) rather than relying on DB-level cascades.
