# DS Chat backend (Phase 1 + 2 + 4 + 5 + 6 + 7 + 8, image uploads, file attachments, admin-configurable upload size limits, emoji & reactions, user profiles, site invites & email, password reset)

FastAPI + SQLAlchemy 2.0 (async) + PostgreSQL + Redis. Implements auth, room
CRUD (open and private), room roles (owner/admin/member) and direct
membership management, a WebSocket chat endpoint that fans out across
multiple app-server instances via Redis pub/sub, Web Push notifications for
offline room members, a site-admin portal (user/room/bot management + an
audit log), a bot/extension layer (scoped API tokens, live bot WebSocket
access, incoming and outgoing webhooks, message editing), image uploads and
generic file attachments in chat messages, emoji reactions on messages,
self-service user profiles
(display name, avatar), self-service password change and a token-based
forgot-password flow, and admin-issued email invites for new accounts
plus email notifications when a user is added to a room. See
`../ARCHITECTURE.md` for the full system design and the phased build plan.

This is an **invite-only site**: there is no public registration endpoint.
Accounts are created by an operator on the app server — see step 4 below.

## Local dev setup

### 1. Postgres

Any local Postgres 14+ works. The quickest option is a container:

```bash
docker run -d --name ds-chat-postgres \
  -e POSTGRES_USER=ds_chat -e POSTGRES_PASSWORD=ds_chat -e POSTGRES_DB=ds_chat \
  -p 5432:5432 postgres:16-alpine
```

Then create the test database (used by the test suite, kept separate from dev data):

```bash
docker exec ds-chat-postgres psql -U ds_chat -d ds_chat -c "CREATE DATABASE ds_chat_test;"
```

(Docker here is purely a local-dev convenience for standing up Postgres quickly —
the actual deployment target has no containers at all, see `ARCHITECTURE.md` §9.)

### 2. Redis

Used for cross-instance WebSocket fan-out and presence (see the section
below). Required — there's no in-memory fallback.

```bash
docker run -d --name ds-chat-redis -p 6379:6379 redis:7-alpine
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

Tests run against a real Postgres database (`ds_chat_test` by default — native
`ENUM`/`UUID` types aren't faithfully reproduced by SQLite) and a real Redis
(db 15 by default, kept separate from dev use of db 0), with each test
wrapped in a transaction that's rolled back afterward:

```bash
DATABASE_URL=postgresql+asyncpg://ds_chat:ds_chat@localhost:5432/ds_chat_test .venv/bin/pytest
```

## Layout

```
app/
  main.py            create_app(), session middleware, router/WS mounting,
                        serves frontend/dist if it exists (see below)
  config.py           environment-driven settings (pydantic-settings)
  database.py          async engine/session, get_db() dependency
  dependencies.py       get_current_user (session cookie or Bearer token),
                           require_room_member, require_room_role,
                           require_site_admin, require_scope
  security.py            argon2 password hashing + token generate/hash (sha256)
  crypto.py               Fernet encrypt/decrypt keyed from SESSION_SECRET --
                             the only reversible secret this app stores in
                             the database (SMTP password), see Site invites
                             & email below
  storage.py              uploaded-image validation (Pillow), downscaling
                             (optionally square-cropped, for avatars), and
                             on-disk save/read -- see Image uploads below
  cli.py                  `python -m app.cli create-user` / `generate-vapid-keys`
  models/                 SQLAlchemy models (users, rooms, room_memberships,
                             messages, message_images, message_reactions,
                             site_invites, password_resets, smtp_settings,
                             push_subscriptions, admin_audit_log, api_tokens,
                             webhooks_incoming, event_subscriptions)
  schemas/                 Pydantic request/response models
  routers/                  auth, rooms, users, signup, push, admin,
                               bots, webhooks, health
  services/                  business logic called by routers
  ws/                        connection_manager (local sockets), presence +
                               broadcaster (Redis), /ws/chat handler
alembic/                      migrations
tests/                         pytest + httpx/TestClient tests
```

## Production deployment (Phase 8)

See [`../DEPLOYMENT.md`](../DEPLOYMENT.md) for the full runbook. The one
piece that lives in this backend's own code: `app/main.py` serves the built
frontend directly (mounts `frontend/dist/assets` with far-future
`Cache-Control` on Vite's content-hashed filenames, and a catch-all route
that serves any other real file under `frontend/dist` or falls back to
`index.html` for client-side routes like `/rooms/<id>` — `index.html`/
`sw.js`/`manifest.webmanifest` always get `Cache-Control: no-cache` instead,
since caching any of those is exactly how a client ends up stuck on a stale
app version after a deploy) — but only if `frontend/dist` exists at
startup. It never does in local dev (the Vite dev server handles the
frontend there instead), so this is fully inert until someone actually runs
`npm run build`. The point: one Gunicorn port ends up serving the frontend
*and* `/api` *and* `/ws`, which is what lets a reverse proxy (Nginx Proxy
Manager, in the deployment this was built for) forward a whole domain to a
single upstream with no custom per-path routing.

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
(`X-DS-Chat-Signature: sha256=...`) on `message.created`/
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

## Room roles and membership (Phase 2)

Rooms can be `open` (anyone can join via `POST /api/rooms/{id}/join`) or
`private` (`is_private: true` at creation — joinable only by being added).
Room roles are `owner` > `admin` > `member`:
- **member**: post messages, leave the room
- **admin**: edit room settings, add/remove plain members
- **owner**: everything admin can, plus delete the room, remove admins, change
  member roles, and transfer ownership

Adding to a private room: an admin+ calls `POST /api/rooms/{id}/members` with
an existing user's `user_id` — this adds them straight to
`room_memberships` (no accept/decline step) and fires a "you've been added"
notification email (see Site invites & email below; silently skipped if
SMTP isn't configured). There used to be a separate accept/decline
`RoomInvite` flow here; it was removed in favor of direct add + notify,
since nothing meaningful was gained by making the target confirm first.
`GET /api/rooms/mine` lists every room (open + private) the current user
belongs to, alongside their role.

## Image uploads

A message can carry an image (`Message.image_id`, nullable), a caption
(`Message.content`, nullable), or both — a `CheckConstraint` requires at
least one. Images live on the app server's local disk (`<repo root>/uploads`,
resolved the same way `app/main.py` locates `frontend/dist` — see
`app/storage.py`), not S3, matching this project's plain-two-servers
deployment; see `../DEPLOYMENT.md` for the production directory and its
(currently missing) backup coverage.

- `POST /api/rooms/{room_id}/images` (room-member gated, multipart) —
  `app/storage.read_capped` rejects (413) as soon as the streamed byte count
  passes 8 MB, before buffering the whole body. `app/storage.process_image`
  then opens the result with Pillow to confirm it's a genuinely decodable
  image (not just a spoofed `Content-Type` header — 400 if not) and
  downscales it so its longer side is ≤2000px, except GIF, left untouched so
  animation isn't collapsed to a single frame. Returns the new
  `message_images` row's id; the frontend attaches it to a message
  afterward, it isn't a message by itself.
- `GET /api/rooms/{room_id}/images/{image_id}` (room-member gated) — 404s if
  the image doesn't belong to that room, otherwise streams it with
  `Cache-Control: private, max-age=31536000, immutable` (content-addressed
  by a generated UUID filename, so once served it never changes).
- The WS `"message"` handler (`app/ws/chat.py`) accepts an optional
  `image_id`, validated against the room before attaching. Push notification
  bodies (`app/services/message_events.py`) say "`{username} sent an image`"
  for an image-only message instead of a body that's just `"username: "`.

Known gap: an uploaded-but-never-sent image (a user attaches a file, then
navigates away before hitting Send) leaks an orphaned file on disk — no
cleanup job for this yet. Not a security issue, since serving still goes
through the same room-membership gate as everything else; just an eventual
disk-space housekeeping item.

## File attachments

A message can also carry a generic file attachment (`Message.file_id`,
nullable, alongside the pre-existing `content` and `image_id`) — a
parallel `MessageFile` model/table, not a generalization of `MessageImage`,
so the working image feature stayed untouched. `app/storage.py`'s
`save_image`/`delete_image` were content-agnostic already (no Pillow
usage) and were renamed to `save_file`/`delete_file` now that both features
share them; `ImageTooLargeError` was likewise renamed to
`UploadTooLargeError`.

- `POST /api/rooms/{room_id}/files` (room-member gated, multipart) — same
  8 MB cap as images (`MAX_FILE_BYTES`, currently an alias of
  `MAX_IMAGE_BYTES`; a real, independently-configurable size-limit redesign
  is a separate later task — see the open file/image size-limit issue), but
  **no content-type allowlist** — arbitrary file types are the point of this
  endpoint, unlike `/images`.
- `GET /api/rooms/{room_id}/files/{file_id}` (room-member gated) — 404s if
  the file doesn't belong to that room, otherwise streams it via
  `FileResponse(..., filename=...)`. Passing `filename=` makes Starlette set
  `Content-Disposition: attachment`, which forces a download in the browser
  regardless of content-type — the deliberate mitigation against a
  user-uploaded `.html`/`.svg` executing script same-origin (session-cookie
  theft) if opened directly. This is why there's no content-type blocklist
  on top of it: forcing a download already neutralizes that whole class of
  risk.
- The WS `"message"` handler and `message_events.py` push-body/broadcast
  logic mirror the image path exactly (an optional `file_id`, validated
  against the room; push body says "`{username} sent a file`" for a
  file-only message).

Same orphaned-upload disk-space caveat as images applies here too.

## Upload size limits

The 8 MB image/file/avatar cap is no longer hardcoded — it's an
admin-configurable site setting (`UploadSettings`, single-row table, same
"fetch-or-create" convention as `SmtpSettings`), editable from the Admin
portal's Settings tab. Unlike `SmtpSettings` (where "no row yet" means
"unconfigured, skip"), a missing row here still needs a usable value, so
`upload_settings_service.get_upload_settings` creates it with the 8 MB
default (`storage.DEFAULT_MAX_UPLOAD_BYTES`) on first read instead of
returning `None`.

- `GET`/`PUT /api/admin/settings/uploads` (site-admin only) — read/update
  the cap. Bounds-checked to 1–500 MB (`UploadSettingsUpdate`) to guard
  against a fat-fingered 0 or an unbounded figure that could exhaust disk.
- `GET /api/uploads/limit` — unlike the admin endpoints, this one is open
  to any authenticated user (same `Depends(get_current_user)`-only pattern
  as `/api/push/vapid-public-key`), since every room member needs to know
  the cap, not just admins. The frontend composer fetches it once per
  mount and rejects an oversized file client-side before ever hitting the
  network; the server still enforces the same value independently via
  `read_capped(file, cap=...)`, so the client-side check is a UX nicety,
  not the actual security boundary.
- All three upload endpoints (room image, room file, avatar) now call
  `get_upload_settings(db)` and pass the live value into `read_capped`
  instead of relying on a module-level constant; their 413 error messages
  interpolate the actual configured limit (`upload_settings_service.
  format_mb`) rather than a hardcoded "8 MB" string.

## Emoji & reactions

An emoji picker in the frontend composer is purely client-side (a static
curated unicode list, no backend involvement). Message **reactions** are
full-stack: `message_reactions` (`app/models/message_reaction.py`) has
`message_id`, `user_id`, `emoji`, and a `UniqueConstraint` on all three
backing toggle semantics — the same user reacting with the same emoji on
the same message twice removes it (Slack/Mattermost convention).
`message_service.toggle_reaction` is a plain select-then-delete-or-insert,
no upsert needed.

WS `"reaction"` envelope (`room_id`, `message_id`, `emoji`) toggles a
reaction; the server broadcasts the message's **full recomputed** reaction
list (`{"type": "reaction_update", "id", "room_id", "reactions": [...]}`),
not an add/remove delta — same approach `message_update` already uses for
edits, keeping client-side state a simple replace rather than a merge.
`GET /{room_id}/messages` embeds each message's `reactions` too
(`message_service.get_reactions_for_messages`, batched, not N+1), so a page
reload doesn't lose reaction state that only ever arrived over WS.

Scope cuts: no outgoing-webhook event type for reactions (`VALID_EVENT_TYPES`
in `webhook_service.py` is unchanged — same restraint as image uploads), no
reaction-count limit or rate limiting, no custom/uploaded emoji (unicode
only, curated client-side list in `frontend/src/lib/emoji.ts`).

## User profiles

Display name and avatar live directly on `User`
(`display_name`, `avatar_filename`, `avatar_content_type`, all nullable) —
no separate profile table, since it's a strict 1:1 with no room-scoping
concern the way message images have. Bio was considered and explicitly
scoped out.

- `PATCH /api/auth/me` — updates `display_name` (`app/routers/auth.py`).
  Empty/whitespace clears it back to `None`, falling back to the username
  everywhere it's displayed.
- `POST /api/auth/me/avatar` / `DELETE /api/auth/me/avatar` — reuse
  `app/storage.py`'s upload primitives (`read_capped`, `process_image`,
  `save_file`) from image uploads, but call `process_image(..., square=True,
  max_dimension=512)` — a new option that center-crops before downscaling,
  since avatars need a fixed square shape at a much smaller size than a
  message image. Unlike message images (which never delete), the previous
  avatar file **is deleted** on replace/remove (`storage.delete_file`) —
  safe to do here because it's strictly one file per user, no accumulation
  risk to accept the way an orphaned message-image upload has.
- `GET /api/users/{user_id}/avatar` (`app/routers/users.py`, new router) —
  serves the file. Two deliberate divergences from the message-image
  serving endpoint: **not** room-membership-gated (avatar visibility
  matches username visibility — any authenticated user can see anyone's),
  and `Cache-Control: private, max-age=300` rather than `immutable` (an
  avatar URL is identity-addressed and its content changes on re-upload,
  unlike a message image's permanent content-addressed URL).

`RoomMemberRead` and `AdminUserRead` both carry `display_name`/
`avatar_filename` so the frontend can render an avatar and a preferred name
anywhere a user appears (message list, room member list, admin Users tab,
TopBar) — `MessageRead` deliberately does **not** carry them; the frontend
resolves both live from the room's member list instead of freezing them
per-message, which is the more correct behavior for a field the sender can
change after the fact.

## Site invites & email

Two related gaps closed together: creating a new account was CLI-only, and
neither a brand-new invitee nor an existing user added to a room got any
notification. Site admins (only) invite a brand-new person by email from
the Admin portal; being added directly to a room (see Room roles and
membership above) sends a "you've been added" email too.

**Email sending** (`app/services/email_service.py`, using `aiosmtplib`):
`send_email(db, to, subject, body)` is the fire-and-forget path used by
invite flows — if `SmtpSettings` isn't configured yet it logs at debug and
returns (same "silently skip if unconfigured" UX push notifications already
use for a missing VAPID key), and it never raises on delivery failure (an
SMTP outage must not block an invite/membership action that already
succeeded in the database). `send_test_email(db, to)` is the one exception —
used only by the admin "send test email" button, it raises so the UI can
show *why* it failed instead of a silent no-op. Plain-text bodies only, no
HTML templates, matching this codebase's existing minimalism.

**SMTP configuration** (`app/models/smtp_settings.py`, `app/routers/admin.py`'s
`/settings/smtp` endpoints) lives in the database, not the env file — the
Admin Settings tab edits it at runtime with no redeploy. It's the first
reversible secret this app stores in the database (`password_hash` is
one-way, API tokens are looked up by hash and never decrypted), so it's
encrypted at rest via `app/crypto.py`: a Fernet key derived from the
already-required `SESSION_SECRET` rather than a new env var. A blank
password on update means "keep the current one" — the frontend never has
the plaintext to send back, only whether one is set (`has_password`).

**Site invites** (`app/models/site_invite.py`, `app/services/site_invite_service.py`) —
distinct from adding an existing user to a room: this targets an email
address for the site, no room involved. The raw token exists only in the
email link, stored hashed (`security.hash_token`, the same convention API
tokens use — it's a bearer secret looked up by itself). `POST /api/signup`
(`app/routers/signup.py`) is the first genuinely public,
unauthenticated endpoint in this app that creates a `User` row — it calls
the existing `auth_service.register_user` directly for identical
hashing/uniqueness handling, and logs the new user in immediately (same
session-cookie line `auth.py`'s `login()` uses) so they land in the app
already signed in. No new rate limiting on it — the unguessable, single-use,
expiring token is the actual protection, inheriting the same "no rate
limiting on human/bot traffic" gap already documented below, not a new one.

**Room-membership email**: `room_service.add_member` sends one email to
the target user after creating the `RoomMembership`, using the live
request's `base_url` for the link — no new "public URL" config needed.

Scope cuts: no outgoing-webhook event type for these (matching image
uploads/reactions), no resend for a site invite (revoke + re-invite covers
it), no HTML email templates.

## Self-service password change and reset

Two related, previously-missing pieces: a logged-in user changing their own
password, and a "forgot password" flow for someone locked out.

**Change password** (`PATCH /api/auth/password`, authenticated) — takes
`current_password` + `new_password`; verifies the current one with
`security.verify_password` before setting `password_hash =
hash_password(new_password)`. Same self-service shape as `PATCH /api/auth/me`
(profile update): mutate `current_user`, commit, done. No session
invalidation elsewhere (there's no server-side session table to invalidate
against — see Notes below), so other logged-in sessions for that account
stay valid until they expire naturally.

**Forgot password** (`app/models/password_reset.py`,
`app/services/password_service.py`) — same hashed-token-with-expiry shape as
site invites, but a shorter 15-minute lifetime (a reset link is meant to be
used immediately, unlike a signup invite someone might not open for days) and
a boolean `used` flag instead of an enum (there's no third state to track).
`POST /api/auth/forgot-password` always returns `204`, whether or not the
email matched an account — the response must never reveal which emails are
registered, so a miss is a silent no-op (no row created, no email sent) after
a single `SELECT`. `GET /api/auth/reset-password/validate` lets the frontend
show a "this link is invalid" state before rendering the password form.
`POST /api/auth/reset-password` completes it and — like signup — logs the
user in immediately (`request.session["user_id"]`), since they've just proven
they control the account's email.

Scope cuts: no rate limiting on `/forgot-password` (inherits the same
documented gap as every other endpoint below, not a new one — the
unguessable expiring token is the actual protection once a request is made),
no cleanup job for expired/used `password_resets` rows (same as
`site_invites`, which has never had one either).

## Notes / scope decisions

- Invite-only site registration: no `POST /api/auth/register`. Accounts are
  provisioned with `python -m app.cli create-user` (see step 4 above), or via
  a site invite (see Site invites & email below). This is separate from
  adding an existing user to a private room — site accounts vs. room
  membership.
- Sessions are signed cookies (Starlette `SessionMiddleware`), not a server-side
  session table — see `ARCHITECTURE.md`'s rationale (simplest way to carry auth
  through a WebSocket handshake). This means there's currently no way to force-
  revoke a session server-side; that needs a real session table later.
- No CSRF token yet — `SameSite=Lax` cookies plus a same-origin frontend dev
  proxy (see `../frontend/vite.config.ts`) is the accepted phase-1 mitigation.
- Deleting a room explicitly deletes its messages/memberships first
  (`room_service.delete_room`) rather than relying on DB-level cascades.
- `admin_audit_log` has no admin UI for filtering/searching yet — it's a
  flat newest-first list with `limit`/`offset` pagination, no filter by
  actor/action/target. Fine at current scale; revisit if the log grows.
