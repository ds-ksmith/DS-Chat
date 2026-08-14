# KeepItTalking backend (Phase 1 + 2)

FastAPI + SQLAlchemy 2.0 (async) + PostgreSQL. Implements auth, room CRUD
(open and private), room roles (owner/admin/member) and invites, and a
single-instance WebSocket chat endpoint. See `../ARCHITECTURE.md` for the
full system design and the phased build plan.

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

### 2. Python environment

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
cp .env.example .env
# edit .env: set SESSION_SECRET to a long random string, e.g.
#   python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

### 3. Migrations

```bash
.venv/bin/alembic upgrade head
```

### 4. Create a user

There's no public sign-up. Create accounts directly with the CLI (add
`--admin` to grant `is_site_admin`, useful ahead of the phase-6 admin portal):

```bash
.venv/bin/python -m app.cli create-user alice alice@example.com "some-password"
```

### 5. Run the dev server

```bash
.venv/bin/uvicorn app.main:app --reload
```

API docs: http://localhost:8000/docs. WebSocket chat endpoint: `ws://localhost:8000/ws/chat`.

### 6. Run tests

Tests run against a real Postgres database (`chatapp_test` by default — native
`ENUM`/`UUID` types aren't faithfully reproduced by SQLite), with each test
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
  cli.py                  `python -m app.cli create-user` (account provisioning)
  models/                 SQLAlchemy models (users, rooms, room_memberships,
                             messages, room_invites)
  schemas/                 Pydantic request/response models
  routers/                  auth, rooms, invites, health
  services/                  business logic called by routers
  ws/                        WebSocket connection manager + /ws/chat handler
alembic/                      migrations
tests/                         pytest + httpx/TestClient tests
```

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
