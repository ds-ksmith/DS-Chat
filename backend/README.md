# DS Chat backend (Phase 1 + 2 + 4 + 5 + 6 + 7 + 8, image uploads, file attachments, admin-configurable upload size limits, emoji & reactions, user profiles, site invites & email, password reset, direct messages, active sessions)

FastAPI + SQLAlchemy 2.0 (async) + PostgreSQL + Redis. Implements auth
(server-side, revocable sessions — see Active sessions below), room CRUD
(open and private), room roles (owner/admin/member) and direct membership
management, direct messages, a WebSocket chat endpoint that fans out across
multiple app-server instances via Redis pub/sub, Web Push and email
notifications for offline room members (plus a native desktop-notification
bridge for DS Chat Desktop), a site-admin portal (user/room/bot management +
an audit log), a bot/extension layer (scoped API tokens, live bot WebSocket
access, incoming and outgoing webhooks, message editing), image uploads,
inline-playable video attachments, and generic file attachments in chat
messages, message deletion, emoji reactions (built-in Unicode plus
site-wide custom/uploaded emoji, both usable in reactions and inline in
message text), self-service user profiles (display name, avatar),
self-service password change and a token-based forgot-password flow, and
admin-issued email invites for new accounts plus email notifications when a
user is added to a room. See `../ARCHITECTURE.md` for the full system
design and the phased build plan.

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
                             messages, message_images, message_files,
                             message_reactions, message_mentions,
                             message_room_references, link_previews,
                             custom_emoji, custom_themes, sessions,
                             site_invites, password_resets, smtp_settings,
                             upload_settings, push_subscriptions,
                             admin_audit_log, api_tokens, webhooks_incoming,
                             event_subscriptions)
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

## Desktop notifications

DS Chat Desktop (a separate Electron wrapper, not this repo) has no push
delivery service configured, so it can't receive Web Push. Instead,
`app/services/message_events.py`'s existing offline-member computation
(`room members - Presence.connected_user_ids(room_id) - {sender}` — the
same audience Web Push uses, described above) also broadcasts a
`desktop_notification` WS envelope (`{type, id, room_id, title, body}`,
`id` being the message's own id so the client can dedupe across
reconnects) to every eligible offline member over their already-open
authenticated socket, unconditionally — the server has no notion of which
clients are running inside Electron. It's sent alongside the Web Push
send, not instead of it, so a member with only a browser tab open is
unaffected.

The client decides whether to act on it: `frontend/src/lib/desktopBridge.ts`
feature-detects `window.dsDesktop` (the bridge Electron's preload script
exposes, per-method rather than via user-agent sniffing — an older wrapper
build may be missing individual methods) and only calls
`showNotification` when the bridge is present and the user's
localStorage-backed preference (`ds-chat-desktop-notifications-enabled`,
default on) allows it. This preference is deliberately a plain client-side
flag rather than reusing `PushSubscription` — desktop notifications need
no server round trip to enable/disable, unlike a push subscription which
has a row to create/delete. `frontend/src/components/DesktopNotificationBridge.tsx`
is mounted once, as a sibling of the routed pages inside the `user.id`-keyed
`ChatSocketProvider`, so it subscribes exactly once per authenticated
session; it also wires `window.dsDesktop.onNotificationClick` to navigate
to the notification's room.

No `User`/`PushSubscription` schema change was needed for this feature —
the only backend change is the new `desktop_notification` envelope type,
covered by `backend/tests/test_desktop_notifications.py`.

## Email notifications for missed messages

Two related, separately-scoped email triggers layered on top of Web Push/
desktop notifications, both in `app/services/message_events.py`:

**DMs** (`_maybe_email_dm_notification`) — always on, no opt-in toggle.
Emails a DM's other participant when they're *genuinely* offline
(`GlobalPresence.is_online`, not just "not connected to this room's own
channel" the way the Web Push/desktop-notification audience is computed —
someone actively using the app in a different room shouldn't get emailed
for a DM) or have `appear_offline` set. Debounced to the first unread
message in the conversation, not one email per message in a burst, by
checking whether any other unread message already exists in the room
since the recipient's `last_read_at`.

**Regular rooms** (`_maybe_email_room_notifications`) — opt-in per
member, per room (`RoomMembership.email_notifications`, toggled via `PATCH
/api/rooms/{id}/notifications`; rejected for a DM — `CannotModifyDmError`
→ 400 — since DMs already get the always-on behavior above). Two triggers,
not one: the room's first unread message debounces the same way DMs do,
*but* a message that `@mentions` the subscriber always emails regardless
of that debounce — a mention is a stronger, individually-addressed signal
that shouldn't get silently absorbed by an earlier plain message in the
same burst already having used up the "first unread" email.

Both paths go through the same `email_service.send_email` used by
invites/room-membership notifications above, so they're silently skipped
if SMTP isn't configured and never block message delivery on an SMTP
outage.

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

## Direct messages

A DM is a `Room` with `is_dm=True` and a deterministic, never-shown
internal `name` (`dm_room_name(user_a, user_b)` — the two user ids sorted
and joined, so it's the same string regardless of who initiates), not a
separate model — `POST /api/rooms/dm` (`find_or_create_dm`) looks up an
existing DM by that name and creates one (`is_private=True`, both
participants as plain `member`) only if none exists yet, so starting a DM
with the same person twice always resolves to the one conversation. The
frontend never renders `Room.name` for a DM; `MyRoomItem.dm_partner`
(`DmPartnerInfo`: the *other* participant's id/username/display
name/avatar/status) is precomputed server-side instead, batched per
request rather than N+1.

**Hiding a DM**: `RoomMembership.hidden_at` lets one participant remove a
DM from their own sidebar without touching the other participant's copy or
deleting anything — a DM has no sensible "leave" (it would violate
`find_or_create_dm`'s exactly-two-members assumption). `POST
/api/rooms/{id}/hide` sets it; it's cleared automatically (un-hiding the
DM) whenever a new message arrives in it or `find_or_create_dm` resolves
back to an already-hidden one — both count as the conversation being
active again, matching how a re-opened DM in Slack/Discord reappears on
its own rather than needing an explicit "unhide."

## Message deletion

`DELETE`-shaped over WS (`{"type": "delete", "room_id", "message_id"}`,
`message_service.delete_message`) — author-only (`NotMessageAuthorError` →
error frame otherwise, no admin/moderator override yet). A real delete of
content, not a UI-only hide: `content`, `image_id`, `file_id`, and
`preview_url` are all cleared and any attached `MessageImage`/`MessageFile`
row (plus its on-disk file) is actually removed, only `deleted_at` (and
`id`/`room_id`/`user_id`/`created_at`, so the tombstone still occupies its
place in history) survives. The attachment's storage filename is read and
the DB row/file only unlinked *after* a successful commit — same ordering
`delete_room` already uses, so a rolled-back transaction never leaves an
already-destroyed file with no way back. Broadcasts
`{"type": "message_deleted", "id", "room_id"}`; the frontend renders a
"message deleted" placeholder rather than removing the row, so the
conversation doesn't visibly shift when someone deletes something above.

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

**Inline video playback**: a browser-natively-playable video attachment
(`INLINE_SAFE_VIDEO_CONTENT_TYPES` in `app/storage.py` — a strict allowlist,
`video/mp4`/`video/webm`/`video/ogg`, deliberately not "every `video/*`
type") is served *without* the `filename=` param above, so it plays inline
in a `<video>` tag instead of forcing a download — the same reasoning
`MessageImage`'s own always-inline endpoint already relies on: these are
content types a browser only ever interprets as media, never as something
that could execute script, so the `Content-Disposition: attachment`
mitigation doesn't need to apply to them. Anything outside that allowlist
(e.g. `.mov`/`video/quicktime`) still forces a download like any other
file.

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

The built-in emoji picker in the frontend composer is purely client-side (a
static curated unicode list, no backend involvement). Message **reactions**
are full-stack: `message_reactions` (`app/models/message_reaction.py`) has
`message_id`, `user_id`, `emoji`, and a `UniqueConstraint` on all three
backing toggle semantics — the same user reacting with the same emoji on
the same message twice removes it (Slack/Mattermost convention).
`message_service.toggle_reaction` is a plain select-then-delete-or-insert,
no upsert needed. `emoji` is `String(32)`, sized to hold either a raw
unicode glyph or a custom emoji's `:shortcode:` reference (see Custom emoji
below) — the WS reaction envelope's own length check matches this exactly,
not an arbitrary smaller cap.

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
reaction-count limit or rate limiting.

## Custom emoji

Site-wide (not room-scoped), uploadable by any authenticated user —
distinct from the built-in Unicode picker above. `CustomEmoji`
(`app/models/custom_emoji.py`): `shortcode` (unique, 30 chars max — sized
so a `:shortcode:` reference fits `MessageReaction.emoji`'s column
alongside its own colons with zero width change), `storage_filename`,
`content_type`, `uploaded_by`.

- `POST /api/custom-emoji` (multipart: `shortcode` form field + `file`) —
  reuses `app/storage.py`'s upload primitives (`read_capped`,
  `process_image(..., square=True, max_dimension=128)`, `save_file`), same
  pattern as avatars. Shortcode format (`^[a-z0-9_-]{2,30}$`) and
  uniqueness are checked *before* processing/saving the image, so a
  rejected upload never orphans a file on disk.
- `GET /api/custom-emoji` — full list, any authenticated user.
- `DELETE /api/custom-emoji/{id}` — the uploader or a site admin only
  (`NotEmojiOwnerError` → 403 otherwise).
- `GET /api/custom-emoji/{shortcode}/image` — serves the file,
  `Cache-Control: private, no-cache` (not `immutable`, and deliberately
  *not* a long `max-age` either — a shortcode can be deleted and
  re-uploaded with different image data under the same URL, and a timed
  cache let a browser keep serving the old image for its full duration
  after that happened; `no-cache` forces revalidation on every use, still
  cheap since `FileResponse`'s own `ETag`/`Last-Modified` make an
  unchanged file a 304, not a full re-transfer).

A `:shortcode:` reference is stored/sent as literal text everywhere (message
content, reaction values) and resolved to an image only at render time on
the frontend — the same convention the built-in Unicode shortcode
autocomplete already used for glyphs, extended to a case with no unicode
codepoint to substitute. No server-side collision check against the ~950
built-in shortcode names (that list only exists in the frontend); the
upload UI warns about a colliding name but doesn't hard-block it.

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
`send_email(db, to, subject, paragraphs, *, cta_label=None, cta_url=None,
theme_user=None)` is the fire-and-forget path used by invite/notification
flows — if `SmtpSettings` isn't configured yet it logs (at `.warning`, not
`.debug` — this app has no logging config lowering the root level below
Python's own `WARNING` default, so anything below that is silently
invisible in production) and returns, and it never raises on delivery
failure (an SMTP outage must not block an invite/membership/notification
action that already succeeded in the database). `send_test_email(db, to)`
is the one exception — used only by the admin "send test email" button, it
raises so the UI can show *why* it failed instead of a silent no-op.
`paragraphs` (a `list[str]`, not a flat `body: str`) renders both an HTML
email — styled with `theme_user`'s own selected theme palette when given,
falling back to the default palette — and a plain-text fallback part from
the same source, rather than a single pre-formatted string that can't
cleanly become HTML without re-parsing it.

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
hashing/uniqueness handling, then `session_service.start_session` (see
Active sessions below) so they land in the app already signed in. No new
rate limiting on it — the unguessable, single-use, expiring token is the
actual protection, inheriting the same "no rate limiting on human/bot
traffic" gap already documented below, not a new one.

`POST /api/admin/invites/{id}/resend` (site-admin only,
`resend_site_invite`) issues a fresh token and resets the 7-day expiry
rather than re-sending the original link — the old link stops working the
moment this runs, and it means resending something close to expiring buys
the full week again, not just whatever was left. Only valid for a still-
`pending` invite (`SiteInviteNotPendingError` otherwise).

**Room-membership email**: `room_service.add_member` sends one email to
the target user after creating the `RoomMembership`, using the live
request's `base_url` for the link — no new "public URL" config needed.

Scope cuts: no outgoing-webhook event type for these (matching image
uploads/reactions).

## Self-service password change and reset

Two related, previously-missing pieces: a logged-in user changing their own
password, and a "forgot password" flow for someone locked out.

**Change password** (`PATCH /api/auth/password`, authenticated) — takes
`current_password` + `new_password`; verifies the current one with
`security.verify_password` before setting `password_hash =
hash_password(new_password)`. Same self-service shape as `PATCH /api/auth/me`
(profile update): mutate `current_user`, commit, done. Doesn't proactively
revoke any other logged-in session for that account — a session table now
exists (see Active sessions below), but changing your password doesn't
walk it and revoke everything else; if you suspect a specific device, use
Active sessions to revoke it directly instead.

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
user in immediately (`session_service.start_session`, see Active sessions
below), since they've just proven they control the account's email.

Scope cuts: no rate limiting on `/forgot-password` (inherits the same
documented gap as every other endpoint below, not a new one — the
unguessable expiring token is the actual protection once a request is made),
no cleanup job for expired/used `password_resets` rows (same as
`site_invites`, which has never had one either).

## Active sessions

Replaces the previously-stateless signed cookie (a bare `user_id`) with a
real server-side `Session` table (`app/models/session.py`) — the cookie
now only ever carries an opaque session id, resolved against this table
via `session_service.resolve_session` on *every* request (`get_current_user`
in `app/dependencies.py`, and the WS handshake in `app/ws/chat.py`), which
is the single choke point that makes revocation actually take effect on a
session's very next request rather than only once its cookie happens to
expire.

Each row records `ip_address` (`X-Forwarded-For`'s first entry, since
production sits behind Nginx Proxy Manager — falls back to the direct peer
address with nothing in front locally), `user_agent`, `created_at`, and a
throttled `last_seen_at` (only bumped if stale by more than 5 minutes —
`get_current_user` resolves a session on every authenticated request, so
writing on every single one would turn a read into a write storm for no
real benefit). `session_service.start_session` is the one place every
"log this browser in" call site (login, signup completion, password-reset
completion) creates the row and stashes its id in the cookie.

- `GET /api/auth/sessions` — every non-revoked session for the current
  user, newest-last-seen first, with a parsed "Browser on OS" label
  (`app/services/user_agent_service.py` — plain substring checks against
  the User-Agent header, no new dependency; special-cases an `Electron/`
  token as "DS Chat Desktop" rather than the underlying Chromium version)
  and `is_current` (compares against `request.state.session_id`, set by
  `get_current_user`) so the frontend can label "this device" and treat
  revoking it as a self-logout.
- `DELETE /api/auth/sessions/{id}` — any of the current user's own
  sessions, including their own current one (a remote sign-out of the
  same device is a legitimate thing to do); 404 if it belongs to someone
  else or is already revoked.
- `POST /api/auth/logout` also revokes the session row, not just clears
  the cookie (`revoke_session_unchecked` — no ownership check needed,
  since a session can only ever log itself out, and never fails even if
  the row is already gone).

Scope cuts: changing your password doesn't proactively revoke other
sessions (see Self-service password change and reset above) — this is a
deliberate scope boundary, not an oversight, since it's a meaningfully
different feature (auto-revoke-everywhere-on-password-change) from
"let a user see and manually revoke what's logged in."

## Link previews

Slack/Discord-style unfurling: the first `http(s)://` URL found in a
message's `content` (`link_preview_service.extract_first_url`) gets a small
preview card fetched from that page's Open Graph tags (`og:title`,
`og:description`, `og:image`, `og:site_name`, falling back to `<title>`).

- **Never blocks the send.** `create_message` extracts and stores the URL
  on `Message.preview_url` synchronously (cheap, no I/O), but the actual
  fetch runs in a background `asyncio.create_task` from
  `message_events.broadcast_new_message`/`broadcast_message_update`, on its
  own DB session (`async_session_factory()`, never the caller's session —
  see `push_service.send_push_to_user`'s docstring for why sharing a
  session across a fire-and-forget task is unsafe). Once it resolves, a
  separate `"link_preview"` WS envelope carries the result to the room;
  the initial `"message"`/`"message_update"` broadcast always has
  `link_preview: null`.
- **SSRF protection is the real security boundary here**, more so than for
  outgoing webhooks — a webhook's `target_url` is admin-configured, but a
  link-preview URL comes from *any* room member's message content. Reuses
  `app/services/ssrf.py`'s `validate_target_url` (originally webhook-only,
  the exception renamed from `UnsafeWebhookUrlError` to `UnsafeUrlError`
  now that it's shared), but re-validates before **every hop** of a
  redirect chain instead of once up front — redirects are followed
  manually (`httpx.AsyncClient(follow_redirects=False)`) specifically so
  each intermediate URL is checked before it's ever connected to, not
  after. Same accepted DNS-rebinding gap as the webhook case (see that
  module's docstring); response body capped at 512 KB and only fetched if
  `Content-Type` is `text/html`.
- **Cached by URL, not by message** (`link_previews` table, unique on
  `url`) — a URL posted by five different people in five different rooms
  within the same short window fetches once. A row also gets written on a
  *failed* fetch (`fetch_failed=True`) so a URL that genuinely doesn't
  unfurl (SSRF rejection, timeout, no usable title) isn't re-attempted on
  every message that references it; both kinds expire after 5 minutes
  (`_CACHE_TTL` — #70: was 7 days, confirmed live as far too long, a
  re-posted URL whose title/content had genuinely changed kept showing
  the stale first-fetch preview for up to a week).
- Parsed with stdlib `html.parser.HTMLParser`, not a new dependency — only
  meta-tag scraping is needed, not general HTML parsing.
- Editing a message re-extracts the URL; if it changed or was removed, the
  frontend clears the now-stale preview immediately (`preview_url` on the
  `message_update` envelope) rather than leaving the old one showing while
  a new fetch (if any) is in flight.
- Scope cuts: one preview per message (the first URL only, matching the
  issue's "a small preview" framing), no way to dismiss/suppress a preview
  before sending, no re-fetch-on-demand if a cached preview goes stale
  mid-TTL.

## Notes / scope decisions

- Invite-only site registration: no `POST /api/auth/register`. Accounts are
  provisioned with `python -m app.cli create-user` (see step 4 above), or via
  a site invite (see Site invites & email above). This is separate from
  adding an existing user to a private room — site accounts vs. room
  membership.
- Sessions are backed by a real server-side table (`app/models/session.py`,
  see Active sessions above) — the signed cookie (Starlette
  `SessionMiddleware`) now only ever carries an opaque session id, resolved
  against that table on every request, which is what makes revocation
  possible. Carrying auth through the WebSocket handshake automatically is
  still why it's cookie-based at all, per `ARCHITECTURE.md`'s original
  rationale.
- No CSRF token yet — `SameSite=Lax` cookies plus a same-origin frontend dev
  proxy (see `../frontend/vite.config.ts`) is the accepted phase-1 mitigation.
- Deleting a room explicitly deletes its messages/memberships first
  (`room_service.delete_room`) rather than relying on DB-level cascades.
- `admin_audit_log` has no admin UI for filtering/searching yet — it's a
  flat newest-first list with `limit`/`offset` pagination, no filter by
  actor/action/target. Fine at current scale; revisit if the log grows.
