# KeepItTalking backend (Phase 1)

FastAPI + SQLAlchemy 2.0 (async) + PostgreSQL. Implements auth, open-room CRUD,
and a single-instance WebSocket chat endpoint. See `../ARCHITECTURE.md` for the
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
  dependencies.py       get_current_user, require_room_member
  security.py            argon2 password hashing
  cli.py                  `python -m app.cli create-user` (account provisioning)
  models/                 SQLAlchemy models (users, rooms, room_memberships, messages)
  schemas/                 Pydantic request/response models
  routers/                  auth, rooms, health
  services/                  business logic called by routers
  ws/                        WebSocket connection manager + /ws/chat handler
alembic/                      migrations
tests/                         pytest + httpx/TestClient tests
```

## Notes / scope decisions

- Invite-only: no `POST /api/auth/register`. Accounts are provisioned with
  `python -m app.cli create-user` (see step 4 above). A more self-service
  invite flow (per-user tokens, or an admin-portal "generate invite" button)
  is a natural phase-2/6 follow-up, not built now.
- Sessions are signed cookies (Starlette `SessionMiddleware`), not a server-side
  session table — see `ARCHITECTURE.md`'s rationale (simplest way to carry auth
  through a WebSocket handshake). This means there's currently no way to force-
  revoke a session server-side; that needs a real session table later.
- No CSRF token yet — `SameSite=Lax` cookies plus a same-origin frontend dev
  proxy (see `../frontend/vite.config.ts`) is the accepted phase-1 mitigation.
- `rooms.is_private` exists in the schema but the API never sets it `True` yet;
  private rooms/invites are phase 2 (tracked as a Gitea issue).
