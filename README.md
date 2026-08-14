# KeepItTalking

A web-based team chat service (Mattermost-style, no threaded conversations),
invite-only. See [ARCHITECTURE.md](ARCHITECTURE.md) for the full system design
and phased build plan.

**Phase 1** (this state of the repo): auth, open-room CRUD, and single-instance
WebSocket chat, backend + a minimal frontend. Later phases (private rooms,
push notifications, Redis fan-out, the admin portal, the bot/extension
system, and production deployment) are tracked as issues in the repo's issue
tracker, prioritized.

## Structure

- [`backend/`](backend/) — FastAPI + SQLAlchemy 2.0 (async) + PostgreSQL. See
  [`backend/README.md`](backend/README.md) for local setup, migrations, and
  how to create a user (registration is invite-only — there's no public
  sign-up endpoint).
- [`frontend/`](frontend/) — React + Vite PWA (login, room list, chat view).

## Quickstart

```bash
# 1. Postgres (see backend/README.md for details)
docker run -d --name chatapp-postgres \
  -e POSTGRES_USER=chatapp -e POSTGRES_PASSWORD=chatapp -e POSTGRES_DB=chatapp \
  -p 5432:5432 postgres:16-alpine

# 2. Backend
cd backend
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
cp .env.example .env   # then set SESSION_SECRET
.venv/bin/alembic upgrade head
.venv/bin/python -m app.cli create-user alice alice@example.com "some-password"
.venv/bin/uvicorn app.main:app --reload &

# 3. Frontend (in another shell)
cd frontend
npm install
npm run dev
```

Then open http://localhost:5173 and log in with the account created above.
The Vite dev server proxies `/api` and `/ws` to the backend on `:8000`, so no
CORS configuration is needed in development.

## Deployment

Not part of Phase 1. The target is two plain Linux servers with no
containers — see [ARCHITECTURE.md §9](ARCHITECTURE.md#9-deployment-architecture--two-linux-servers-no-docker)
and the corresponding "Production deployment" issue in the tracker.
