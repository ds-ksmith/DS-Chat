# Chat service — architecture document

## 1. Overview

A web-based team chat service, similar in spirit to Mattermost, with no threaded
conversations. Core features:

- Chat rooms that are either **open** (anyone can join) or **invite-only** (private)
- A **PWA** client — single codebase serves desktop, mobile web, and an installable
  app experience
- **Push notifications** for offline/backgrounded users
- A **full admin portal** for site administration
- An **extension system** for bots and AI agents (webhooks, scoped API tokens,
  live WebSocket access)

Deployment target: two plain Linux servers, no containers. One server runs the
database and Redis; the other runs the application and serves the frontend.

## 2. Tech stack

| Layer | Choice | Why |
|---|---|---|
| Backend | Python, FastAPI (async) | Async-native, fits many concurrent WebSocket connections without extra layers |
| ORM / migrations | SQLAlchemy 2.0 (async) + Alembic | Mature async ORM, explicit schema migrations |
| Database | PostgreSQL | Relational structure fits users/rooms/memberships/messages well |
| Cross-instance broadcast | Redis (pub/sub) | Lets multiple app server processes fan out messages to all connected clients |
| Push notifications | pywebpush + VAPID | Standard Web Push, works on Android and iOS 16.4+ (PWA must be installed to home screen on iOS) |
| Frontend | React + Vite, vite-plugin-pwa | Generates the manifest and service worker for install + push |
| Reverse proxy / TLS | Nginx + Let's Encrypt (certbot) | Terminates TLS, serves static assets, proxies REST + WebSocket traffic |
| Process management | systemd | No Docker — native to the target Linux distro, no extra install |
| Auth | Session cookies (httpOnly, secure) | Simplest to carry through a WebSocket handshake automatically |

## 3. System architecture

### 3.1 Core message flow

```
PWA client (browser + service worker)
        |  REST + WebSocket
        v
FastAPI app server (N instances behind Nginx)
        |            |                |
        v            v                v
  PostgreSQL     Redis pub/sub    Push service (pywebpush)
  (persistence)  (fan-out across   (delivers to offline
                  app instances)    clients via Web Push)
```

A message is persisted to Postgres, published to a Redis channel scoped to its
room, and every app server instance subscribed to that channel forwards it over
WebSocket to its own connected clients who are members. Members who are not
currently connected get a Web Push notification instead, looked up from their
stored push subscription.

Redis only matters once more than one app server process is running. A single
instance can skip it entirely and add it later without changing anything else.

### 3.2 Admin and extension layer

```
Admin portal          Bots / AI agents
     |                       |
     v                       v
        API gateway
   (scoped tokens + admin role checks)
                 |
                 v
        Core chat server
   (rooms, messages, permissions)
                 |
                 v (WebSocket events, dashed = async)
        back out to bots/agents
```

Admin portal and bots/agents are both just API consumers, differentiated by the
credentials they carry: session + `is_site_admin` flag for the portal, scoped API
tokens for bots. Bots can also hold a live WebSocket connection to receive room
events in real time and post message updates — the same mechanism a human client
uses.

## 4. Data model

```
users
  id, username, email, password_hash, is_bot, is_site_admin, created_at

rooms
  id, name, description, is_private, owner_id, created_at

room_memberships
  room_id, user_id, role (owner | admin | member), joined_at

room_invites
  id, room_id, invited_by, token, target_user_id or target_email,
  expires_at, status (pending | accepted | revoked)

messages
  id, room_id, user_id, content, created_at, edited_at, deleted_at

push_subscriptions
  id, user_id, endpoint, p256dh_key, auth_key, created_at

api_tokens
  id, owner_id (user or bot), token_hash, scopes[], last_used_at, created_at

webhooks_incoming
  id, room_id, token, created_by, description

event_subscriptions
  id, room_id (nullable = global), event_types[], target_url,
  signing_secret, created_by

admin_audit_log
  id, actor_id, action, target_type, target_id, metadata, created_at
```

## 5. Permission model

- **Room visibility**: `open` (any authenticated user can find and join) or
  `private` (visible only to members, joinable only via invite).
- **Room roles**: `owner` (delete room, transfer ownership), `admin` (invite/remove
  members, edit settings), `member` (post, leave).
- **Site-level**: `is_site_admin` on the user record, checked for every admin
  portal route.
- Every room action is authorized server-side against `room_memberships` — never
  trust a client's claim about its own role or membership.

## 6. Real-time and push notification flow

1. Client sends a message over its open WebSocket.
2. Server checks the sender is a member of the room, persists the message.
3. Server publishes the message to the room's Redis pub/sub channel.
4. Every app instance subscribed to that channel forwards it to its own connected
   members over WebSocket.
5. For members with no active connection, the server looks up
   `push_subscriptions` and sends a Web Push notification via `pywebpush`.

## 7. Extension system: bots and AI agents

Extensions run **outside** the server process and talk to it over the network —
no in-process plugin runtime, no sandboxing to build. This is deliberately the
lighter-weight option, and it matches how AI agents naturally integrate: as an
HTTP/WebSocket client.

- **Bot accounts**: a row in `users` with `is_bot = true`. Can be added to rooms
  and post messages exactly like a human account.
- **Scoped API tokens**: e.g. `read:messages`, `write:messages`, `manage:rooms`,
  issued per bot from the admin portal, hashed at rest, shown once at creation.
- **Incoming webhooks**: a room-scoped URL an external service can POST a message
  to. No auth flow beyond the URL being a secret.
- **Outgoing webhooks / event subscriptions**: the server POSTs to a registered
  URL when matching events happen, signed with `signing_secret` so the receiver
  can verify authenticity.
- **Live WebSocket access for bots**: same connection type the PWA client uses,
  authenticated with a bot token. Lets a bot or AI agent see messages as they
  arrive and reply without polling.
- **Message update events**: beyond create/edit/delete, support patching an
  existing message's content. This lets an AI agent post a placeholder and stream
  tokens into it live, the same pattern Slack/Discord bots use.

Security notes: validate outgoing webhook target URLs to block requests into
internal network ranges (SSRF), rate-limit bot API calls the same as human ones,
and log bot actions to `admin_audit_log`.

## 8. Admin portal

Built as protected routes inside the same React PWA (`/admin/*`), gated by
`is_site_admin` on the session — no separate app or deployment to maintain.

Features:
- User management: list, deactivate, reset password, promote to site admin
- Room management: view all rooms (including private), transfer ownership,
  force-archive
- Bot/integration management: create bots, generate/revoke tokens, set scopes,
  view registered webhooks
- System settings: open vs invite-only registration, file size limits, branding
- Audit log viewer

For fast internal CRUD scaffolding on top of the SQLAlchemy models, consider
[SQLAdmin](https://aminalaee.dev/sqladmin/) mounted on an internal-only path —
useful for raw table management while custom logic (moderation, bot tokens,
audit views) gets built separately.

## 9. Deployment architecture — two Linux servers, no Docker

### 9.1 Data server

Runs PostgreSQL and Redis.

- Bind Postgres and Redis to the private network interface only, never `0.0.0.0`
  on a public interface.
- Firewall (`ufw` or `iptables`): allow port 5432 (Postgres) and 6379 (Redis)
  only from the app server's IP address.
- If the hosting provider doesn't offer a private network between the two
  servers, put a WireGuard tunnel between them and bind services to the tunnel
  interface instead of trusting a firewall rule alone over the public internet.
- Backups: nightly `pg_dump` via a cron job, rotated and shipped off-box.

### 9.2 App server

Runs the FastAPI app and Nginx; serves the built PWA static files.

- Python virtualenv, application installed via `pip install -e .` or similar.
- App run via Gunicorn with Uvicorn workers, one process per CPU core as a
  starting point, managed by a systemd unit:

```ini
# /etc/systemd/system/chatapp.service
[Unit]
Description=Chat service app server
After=network.target

[Service]
User=chatapp
WorkingDirectory=/srv/chatapp
EnvironmentFile=/etc/chatapp/env
ExecStart=/srv/chatapp/venv/bin/gunicorn app.main:app \
  -k uvicorn.workers.UvicornWorker \
  --workers 4 \
  --bind unix:/run/chatapp/chatapp.sock
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

- Nginx terminates TLS (certbot-managed certificate), serves the built frontend
  assets directly, and reverse-proxies API and WebSocket traffic to the Unix
  socket:

```nginx
server {
    listen 443 ssl;
    server_name chat.example.com;

    root /srv/chatapp/frontend/dist;
    try_files $uri /index.html;

    location /api/ {
        proxy_pass http://unix:/run/chatapp/chatapp.sock;
        proxy_set_header Host $host;
    }

    location /ws/ {
        proxy_pass http://unix:/run/chatapp/chatapp.sock;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
    }
}
```

- Secrets (database URL pointing at the data server's private IP, Redis URL,
  VAPID keys, session secret) live in `/etc/chatapp/env`, loaded via
  `EnvironmentFile=`, never committed to the repository.
- Deploy process: `git pull`, install/update dependencies, `alembic upgrade
  head`, build the frontend, `systemctl restart chatapp`, `nginx -s reload` if
  the Nginx config changed.
- Logs: `journalctl -u chatapp`, rotated by systemd/journald defaults; add
  `logrotate` if the app also writes its own log files.

## 10. Security considerations

- Server-side authorization on every room and message action — never trust
  client-supplied role/membership claims.
- Database bound to the private network only, firewalled to the app server's IP.
- API tokens and webhook secrets hashed/stored securely, shown once at creation.
- Outgoing webhook URLs validated against internal IP ranges to prevent SSRF.
- Rate limiting on both human and bot API traffic.
- TLS everywhere in transit (Nginx-terminated for clients; a WireGuard tunnel or
  equivalent for cross-server DB traffic if not on a trusted private network).

## 11. Phased build plan

1. Auth, room CRUD, open rooms, single-instance WebSocket messaging
2. Private rooms, invites, roles
3. PWA shell — manifest, service worker, offline caching
4. Push notification subscription + delivery
5. Redis pub/sub for horizontal scaling across app server instances
6. Admin portal
7. Bot/extension system: tokens, webhooks, bot WebSocket access, message updates
