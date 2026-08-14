# KeepItTalking backend (Phase 1 + 2 + 4 + 5 + 6 + 7)

FastAPI + SQLAlchemy 2.0 (async) + PostgreSQL + Redis. Implements auth, room
CRUD (open and private), room roles (owner/admin/member) and invites, a
WebSocket chat endpoint that fans out across multiple app-server instances
via Redis pub/sub, Web Push notifications for offline room members, a
site-admin portal (user/room/bot management + an audit log), and a bot/
extension layer (scoped API tokens, live bot WebSocket access, incoming and
outgoing webhooks, message editing). See `../ARCHITECTURE.md` for the full
system design and the phased build plan.

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
`--admin` to grant `is_site_admin`, which unlocks the admin portal at
`/admin` on the frontend and the `/api/admin/*` routes below):

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
  dependencies.py       get_current_user (session cookie or Bearer token),
                           require_room_member, require_room_role,
                           require_site_admin, require_scope
  security.py            argon2 password hashing + token generate/hash (sha256)
  cli.py                  `python -m app.cli create-user` / `generate-vapid-keys`
  models/                 SQLAlchemy models (users, rooms, room_memberships,
                             messages, room_invites, push_subscriptions,
                             admin_audit_log, api_tokens, webhooks_incoming,
                             event_subscriptions)
  schemas/                 Pydantic request/response models
  routers/                  auth, rooms, invites, push, admin, bots, webhooks, health
  services/                  business logic called by routers
  ws/                        connection_manager (local sockets), presence +
                               broadcaster (Redis), /ws/chat handler
alembic/                      migrations
tests/                         pytest + httpx/TestClient tests
```

## Admin portal (Phase 6)

Every `/api/admin/*` route (`app/routers/admin.py`) requires
`current_user.is_site_admin` (checked via `require_site_admin`,
`app/dependencies.py`) and is backed by `app/services/admin_service.py`:
- **Users**: list, deactivate/reactivate (`User.is_active`), reset password,
  promote/demote `is_site_admin`. An admin can't deactivate or demote their
  own account (`CannotActOnSelfError` → 400) — the one guard against an
  admin locking themselves out. Deactivation takes effect immediately, even
  for an already-open session: `get_current_user` re-checks `is_active` on
  every request since it already loads the user row.
- **Rooms**: list every room including private ones (unlike the
  member-facing `GET /api/rooms`, which is open-rooms-only), archive/
  unarchive (`Room.is_archived` — archived rooms drop out of the open-room
  browse list but stay readable for existing members, matching how
  Mattermost archive works), and force a transfer of ownership to any
  existing member without needing to already be the owner (the "admin
  override" of the member-initiated transfer in `room_service.py`, which
  otherwise requires exactly that).
- **Audit log**: every mutating admin action writes one `AdminAuditLog` row
  (actor, action, target type/id, JSON metadata) in the same transaction as
  the change, listed newest-first via `GET /api/admin/audit-log`.

Bot/integration management (deferred from this phase originally) is now in
place — see Phase 7 below. One item is still deliberately not here:
- **System settings** — no settings storage or concrete setting exists yet.
  The frontend has an empty "Settings" tab as a placeholder for when one
  does.

## Bot/extension system (Phase 7)

Bots are `User` rows with `is_bot=True` (`app/services/bot_service.py`,
admin-only, `/api/admin/bots/*`) — a generated-and-discarded password since
bots never log in with one, and a `{username}@bots.example.com` placeholder
email (`.local`/`.invalid` are rejected by `EmailStr`'s special-use-TLD
check; a subdomain of the real, if reserved-for-docs, `.com` isn't). A bot
authenticates instead with a **scoped API token** (`read:messages`,
`write:messages`, `manage:rooms`) — shown once at issuance, stored as a
SHA-256 hash (`security.hash_token`, deliberately *not* argon2: a bearer
token has to be looked up by itself with no username to key off first,
which argon2's per-call random salt makes impossible; a fast hash of a
256-bit random token is the standard approach, same as GitHub/Stripe keys).

**Auth**: `get_current_user` (`app/dependencies.py`) checks for an
`Authorization: Bearer` header before falling back to the session cookie;
a resolved token is stashed on `request.state.api_token` so `require_scope`
can gate specific actions. A token-authenticated bot is subject to the
*exact same* room-membership/role checks as a session-authenticated human
on every existing endpoint — the token only narrows things further, it
doesn't grant anything a plain room membership wouldn't. Only
`read:messages`/`write:messages` are actually scope-gated (on
`GET /api/rooms/{id}/messages` and the WS message/edit handlers) —
`manage:rooms` is a recognized, issuable scope with no separate enforcement
yet, so a bot's room-management ability is bounded by its ordinary room
role, same as any user; wiring real `manage:rooms` gating into the dozen
room-management endpoints was cut from this phase's scope (confirmed with
the repo owner) as disproportionate to the win. The WS handshake
(`app/ws/chat.py`) accepts the same header directly (bots set it on the
handshake; browsers use the cookie) — same `/ws/chat` endpoint a human
client uses, per `ARCHITECTURE.md`'s "same connection type" design.

**Message editing**: `{"type": "edit", "room_id", "message_id", "content"}`
over the existing WS connection (`message_service.edit_message` — 403 if
you're not the author), broadcasts `{"type": "message_update", ...}` via the
same `RoomBroadcaster.publish()` new messages use, so it fans out
cross-instance for free. `Message.edited_at` (present in the schema since
Phase 1, unused until now) is exposed on `MessageRead`. The frontend also
gets a minimal "edit your own message" UI affordance (hover a bubble you
own) — not asked for by the issue, but the only practical way to exercise
the pipeline by hand instead of only via a scripted bot client, and it's a
small addition once the WS envelope exists anyway.

**Incoming webhooks** (`POST /api/rooms/{id}/webhooks/incoming`, room-admin
managed, mirrors how invites are nested under rooms): a room-scoped URL
with no auth beyond the token in it being correct
(`webhooks_incoming.token` is stored **in the clear**, unlike API tokens —
the room admin needs to view/copy the full URL anytime). `POST
/api/webhooks/incoming/{token}` (public, no auth dependency) creates a
message attributed to the webhook's creator and runs the identical
post-message pipeline a WS-originated message does
(`app/services/message_events.py`'s `broadcast_new_message`, shared by both
call sites rather than duplicated).

**Outgoing webhooks / event subscriptions** (`POST
/api/rooms/{id}/event-subscriptions`, room-admin managed; room-scoped or
global via `room_id=null`): fires an HMAC-SHA256-signed POST
(`X-KeepItTalking-Signature: sha256=...`) on `message.created`/
`message.updated`, delivered via a backgrounded `asyncio.create_task`
(`app/services/webhook_delivery.py`) — safe to background here, unlike the
Phase 4 push lesson, since there's no DB session involved, just the
already-serialized payload and secret. Fire-once, no retry/backoff — a
failed delivery is logged and dropped, documented limitation, not a
guarantee.

**SSRF protection** (`app/services/ssrf.py`): target URLs are validated at
*subscription-creation time* — non-http(s) schemes rejected, hostname
resolved and rejected if any address is private/loopback/link-local/
reserved/multicast. Not re-validated per delivery, so DNS rebinding between
creation and a later send isn't defended against — a real gap, deliberately
left open (confirmed with the repo owner) rather than building the
meaningfully more involved per-request IP-pinning that would close it.

**Rate limiting**: `ARCHITECTURE.md` calls for rate-limiting bot API calls
the same as human ones. Not implemented — there's no rate limiting
anywhere in the app today (human or bot) to extend, and building one well
is its own scope. Documented gap, not an oversight.

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
message, `app/services/message_events.py` computes `room members -
Presence.connected_user_ids(room_id) - {sender}` (who's actually connected
to *that room* right now, across every app instance — see Phase 5 below;
the sender is subtracted explicitly rather than relied on to be "connected,"
since that's only true for WS-originated messages, not the Phase 7
incoming-webhook path) and sends each offline member a push via `pywebpush`,
awaited inline against the same request-scoped session rather than fired as
a background task — the broadcast to online members already happened by
that point, so nothing online-facing is delayed, and it sidesteps
`asyncio.create_task()`s outliving the session/event loop they were created
on. An expired/invalid subscription (pywebpush 404/410) is deleted
automatically.

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
- `admin_audit_log` has no admin UI for filtering/searching yet — it's a
  flat newest-first list with `limit`/`offset` pagination, no filter by
  actor/action/target. Fine at current scale; revisit if the log grows.
