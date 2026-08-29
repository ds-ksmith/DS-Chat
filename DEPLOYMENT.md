# Deploying DS Chat

Two Debian 13 servers, no containers, matching [ARCHITECTURE.md §9](ARCHITECTURE.md#9-deployment-architecture--two-linux-servers-no-docker):

```
                    Nginx Proxy Manager (elsewhere in your infra --
                    terminates TLS, reverse-proxies to the app server)
                                |
                                v
        App server                          Data server
   Gunicorn + Uvicorn workers  <-------->  PostgreSQL + Redis
   (systemd, port 8000)         private     (private interface only)
   serves the built frontend    network
   + /api + /ws on one port
```

TLS termination and public-facing reverse proxying are **not** handled on
the app server — they're handled by an existing, separate Nginx Proxy
Manager (NPM) instance elsewhere in your infrastructure. The app server just
needs to be reachable on one TCP port by NPM; §5 below covers what to
configure in NPM's own UI.

This assumes you already have SSH access (with sudo) to two Debian 13
machines — no OS-bootstrap/hardening steps here, just app-specific setup.
Package versions referenced below (Python 3.13, PostgreSQL 17, Node.js 20,
`redis-server` 8.0) are what Debian 13's own repos ship as of this writing —
no third-party apt sources needed anywhere in this guide.

Replace every `<PLACEHOLDER>` below with your actual values before running
a command.

## 1. Prerequisites

- A domain (e.g. `chat.example.com`) — DNS and TLS are handled entirely by
  Nginx Proxy Manager, so just make sure NPM itself can already reach the
  app server's address before starting §5.
- The data server and app server can reach each other over your hosting
  provider's private network. Find each box's private IP with `ip addr` —
  ask your provider's docs which interface is the private one if it's not
  obvious (`eth1`, `ens19`, etc. are common).

## 2. Data server: PostgreSQL + Redis

```bash
sudo apt update
sudo apt install -y postgresql redis-server
```

**PostgreSQL** — create the role and database:

```bash
sudo -u postgres psql -c "CREATE ROLE ds_chat WITH LOGIN PASSWORD '<DB_PASSWORD>';"
sudo -u postgres psql -c "CREATE DATABASE ds_chat OWNER ds_chat;"
```

Bind it to the private interface only (find the exact config path with
`sudo -u postgres psql -c 'SHOW config_file;'` if 17 isn't your version):

```bash
sudo sed -i "s/^#\?listen_addresses.*/listen_addresses = 'localhost,<DATA_SERVER_PRIVATE_IP>'/" \
  /etc/postgresql/17/main/postgresql.conf
```

Allow the app server in over the private network — Postgres matches
`pg_hba.conf` rules top-to-bottom, but this one's address is specific
enough (a single `/32`) that it won't collide with Debian's default
`127.0.0.1`/`::1`-only entries, so appending is fine:

```bash
echo "host    ds_chat    ds_chat    <APP_SERVER_PRIVATE_IP>/32    scram-sha-256" \
  | sudo tee -a /etc/postgresql/17/main/pg_hba.conf
sudo systemctl restart postgresql
```

**Redis** — bind to the private interface and require a password
(`/etc/redis/redis.conf`):

```bash
sudo sed -i "s/^bind .*/bind 127.0.0.1 <DATA_SERVER_PRIVATE_IP>/" /etc/redis/redis.conf
sudo sed -i "s/^# requirepass .*/requirepass <REDIS_PASSWORD>/" /etc/redis/redis.conf
sudo systemctl restart redis-server
```

**Firewall** — only the app server's private IP may reach either service:

```bash
sudo apt install -y ufw
sudo ufw allow OpenSSH
sudo ufw allow from <APP_SERVER_PRIVATE_IP> to any port 5432 proto tcp
sudo ufw allow from <APP_SERVER_PRIVATE_IP> to any port 6379 proto tcp
sudo ufw enable
```

**Nightly backups** — see `deploy/backup-postgres.sh`'s own header for the
install steps (copy it to `/usr/local/bin/`, cron entry). Off-box shipping
is left as a placeholder in that script — see §8 below.

## 3. App server: Python, Node.js, the `ds-chat` user, and the app itself

```bash
sudo apt update
sudo apt install -y python3 python3-venv nodejs npm git
```

### 3a. The `ds-chat` system user and directory

```bash
sudo useradd --system --shell /usr/sbin/nologin --home-dir /srv/ds-chat ds-chat
# Deliberately no --create-home: on Debian, --system + --create-home is
# unreliable in *both* directions -- sometimes it silently skips creating
# the directory at all, sometimes it creates it and populates it from
# /etc/skel (.bashrc, .profile, .bash_logout), which then makes the git
# clone in the next step fail since it refuses to clone into a non-empty
# directory. Creating the directory ourselves, with no skel copying,
# sidesteps both failure modes.
sudo mkdir -p /srv/ds-chat
sudo chown ds-chat:ds-chat /srv/ds-chat
```

Deliberately not creating `/srv/ds-chat/uploads` here -- `git clone` in the
next step refuses to clone into a non-empty directory, so anything created
inside `/srv/ds-chat` has to wait until after the clone. (The app would
also create this directory itself on first upload if it were missing --
see `app/storage.py` -- so this step is for clarity/permissions, not a
strict requirement.)

### 3b. Clone the repo (deploy key or access token)

```bash
sudo -u ds-chat mkdir -p /srv/ds-chat/.ssh
sudo -u ds-chat ssh-keygen -t ed25519 -f /srv/ds-chat/.ssh/id_ed25519 -N ""
sudo cat /srv/ds-chat/.ssh/id_ed25519.pub
```

Add that public key as a **read-only deploy key** on the Gitea repo
(Settings → Deploy Keys), then:

```bash
sudo -u ds-chat ssh-keyscan git.darksingularity.org >> /srv/ds-chat/.ssh/known_hosts
sudo -u ds-chat git clone git@git.darksingularity.org:DarkSingularity/ds-chat.git /srv/ds-chat
```

(If your Gitea's SSH is on a non-default port, adjust the clone URL and
`ssh-keyscan -p <port>` accordingly.)

**Alternative: a personal/deployment-user access token instead of a deploy
key** — skip the `.ssh`/`ssh-keygen`/`ssh-keyscan` commands above entirely
and clone over HTTPS with the token embedded in the URL:

```bash
sudo -u ds-chat git clone https://<TOKEN>@git.darksingularity.org/DarkSingularity/ds-chat.git /srv/ds-chat
```

The token then lives in plaintext in `/srv/ds-chat/.git/config` (`git
remote -v` shows it) — readable by root and the `ds-chat` user, not by
anyone else under normal file permissions. `deploy/upgrade.sh`'s later
`git pull`s reuse this same authenticated URL automatically, no extra
setup needed. Fine as long as the token is scoped to read-only access on
just this repo.

Either way, now that the repo is cloned:

```bash
sudo -u ds-chat mkdir -p /srv/ds-chat/uploads
```

### 3c. Backend: venv, env file, migrations, first admin

```bash
sudo -u ds-chat python3 -m venv /srv/ds-chat/backend/.venv
sudo -u ds-chat /srv/ds-chat/backend/.venv/bin/pip install -e /srv/ds-chat/backend
```

```bash
sudo mkdir -p /etc/ds-chat
sudo cp /srv/ds-chat/deploy/ds-chat.env.example /etc/ds-chat/env
sudo chown root:ds-chat /etc/ds-chat/env
sudo chmod 0640 /etc/ds-chat/env
sudo -e /etc/ds-chat/env   # fill in DATABASE_URL, REDIS_URL, SESSION_SECRET (see below)
```

Generate `SESSION_SECRET`:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

Run migrations (as `ds-chat`, with the env file sourced so `DATABASE_URL`
is set) — safe as a single non-interactive command since nothing here is a
user-chosen value that could contain quotes/spaces/special characters:

```bash
sudo -u ds-chat bash -c 'set -a; source /etc/ds-chat/env; set +a; cd /srv/ds-chat/backend && .venv/bin/alembic upgrade head'
```

Creating the first admin account is different — the password is arbitrary
user input, and wrapping it in a second layer of quoting inside the `bash
-c '...'` above is fragile (a space drops the rest of the password as
"unrecognized arguments"; a literal `'` in the password breaks the outer
quoting entirely). Drop into an authenticated shell first instead, so
there's only one layer of quoting to get right, at an actual prompt:

```bash
sudo -u ds-chat bash -c 'set -a; source /etc/ds-chat/env; set +a; exec bash'
```

Then, from inside that shell:

```bash
cd /srv/ds-chat/backend
.venv/bin/python -m app.cli create-user <ADMIN_USERNAME> <ADMIN_EMAIL> "<ADMIN_PASSWORD>" --admin
exit
```

Optional: push notifications. Skipped silently if `VAPID_PUBLIC_KEY`/
`VAPID_PRIVATE_KEY` are left unset in `/etc/ds-chat/env`. To enable:

```bash
sudo -u ds-chat /srv/ds-chat/backend/.venv/bin/python -m app.cli generate-vapid-keys
# paste the three printed lines into /etc/ds-chat/env
```

Optional: outgoing email (admin-invited signups, room membership notifications).
Unlike everything else on this page, SMTP is **not** configured here —
it's set through the Admin portal's Settings tab at runtime, no redeploy or
env file edit needed. Skipped silently (logged, not an error) until an
admin sets it up.

### 3d. Frontend build

`backend/app/main.py` serves `frontend/dist` directly (alongside `/api` and
`/ws`) whenever that directory exists — that's what lets Nginx Proxy
Manager forward the whole domain to one port with no custom path routing.

```bash
sudo -u ds-chat bash -c 'cd /srv/ds-chat/frontend && npm ci && npm run build'
```

### 3e. systemd unit

```bash
sudo cp /srv/ds-chat/deploy/systemd/ds-chat.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now ds-chat
sudo systemctl status ds-chat --no-pager
```

Confirm it's actually up before continuing:

```bash
curl -s http://127.0.0.1:8000/api/health   # expect {"status":"ok"}
```

### 3f. Let `ds-chat` restart its own service (needed for `deploy/upgrade.sh`)

```bash
echo 'ds-chat ALL=(root) NOPASSWD: /usr/bin/systemctl restart ds-chat, /usr/bin/systemctl status ds-chat, /usr/bin/systemctl status ds-chat *' \
  | sudo tee /etc/sudoers.d/ds-chat
sudo chmod 0440 /etc/sudoers.d/ds-chat
sudo visudo -cf /etc/sudoers.d/ds-chat   # validates syntax before it's live
```

The third pattern (`... status ds-chat *`) matters, not just the bare one:
`deploy/upgrade.sh` actually calls `systemctl status ds-chat --no-pager -l`,
and sudoers matches commands on the *exact* argument string unless a
wildcard is present — the bare `status ds-chat` entry alone doesn't cover
those extra flags, so without this it silently falls back to a password
prompt on every upgrade. Since `ds-chat` has no password (correctly — it's
a `nologin` system account), that prompt can never actually be satisfied,
only worked around with Ctrl+C after the (already-succeeded) upgrade.

### 3g. Firewall

Only Nginx Proxy Manager's address may reach port 8000:

```bash
sudo apt install -y ufw
sudo ufw allow OpenSSH
sudo ufw allow from <NPM_IP> to any port 8000 proto tcp
sudo ufw enable
```

If NPM reaches this box over the same private network the data server
uses, bind gunicorn to that private IP instead of `0.0.0.0` in
`deploy/systemd/ds-chat.service` for defense in depth on top of the
firewall rule (edit `--bind`, then `daemon-reload` + `restart`).

## 4. Configuring Nginx Proxy Manager

This is config in NPM's own UI/database, not a file this repo ships:

1. **Proxy Hosts → Add Proxy Host**
2. Domain Names: `chat.example.com`
3. Scheme: `http`, Forward Hostname/IP: the app server's address (private
   IP if reachable from NPM, otherwise its public IP — matches whatever you
   firewalled to NPM's IP in §3g), Forward Port: `8000`
4. **Websockets Support: ON** — without this, `/ws/chat` won't upgrade and
   chat won't work at all. This is the one setting that actually matters
   beyond the basics.
5. **SSL tab**: request a new Let's Encrypt certificate, enable "Force SSL".
   The app has no WS-level ping/pong keepalive, so if NPM's own idle-connection
   timeout ever recycles a quiet chat connection, the client reconnects
   automatically within a few seconds (`frontend/src/ws/useChatSocket.ts`) —
   nothing further to tune here unless you want to avoid that churn entirely,
   in which case raise NPM's proxy read/send timeout in its Advanced tab.
6. Save.

## 5. First-deploy verification

- `curl -s https://chat.example.com/api/health` → `{"status":"ok"}`
- Open `https://chat.example.com` in a browser, log in with the admin
  account from §3c, create a room, send a message, confirm it appears
  live (WebSocket working).
- `sudo journalctl -u ds-chat -f` on the app server while doing the above —
  should show request logs, no tracebacks.

## 6. Upgrades

```bash
sudo -u ds-chat /srv/ds-chat/deploy/upgrade.sh
```

Pulls latest `main`, reinstalls backend deps, runs `alembic upgrade head`,
rebuilds the frontend, restarts `ds-chat`, and curls `/api/health` to
confirm it came back up. Fails loudly (`set -euo pipefail`) and stops
before restarting anything if an earlier step — most importantly a failed
migration — errors out, so a bad deploy doesn't take down the previously
working one.

Active users get disconnected for a few seconds during the restart and
reconnect automatically (same reconnect logic as §4's NPM-timeout note) —
expected, not a bug.

**Rollback**: if a deploy goes bad, `git log` to find the last-good commit,
`git checkout <commit>` on the app server, then re-run the relevant parts of
`deploy/upgrade.sh` manually (skip the migration step if the bad deploy's
migration needs to stay applied — there's no automated downgrade story here,
matching how Alembic is used everywhere else in this project: forward-only
in practice, downgrades written and tested by hand if one is ever needed).

## 7. Backups

`deploy/backup-postgres.sh` (installed in §2) runs nightly via cron,
producing a gzipped `pg_dump` in `/var/backups/ds-chat/` with 14-day local
rotation. Off-box shipping is a placeholder in that script (commented-out
rsync/S3 examples) — decide where those need to go and fill it in.

That script covers Postgres only. Uploaded chat images, file/video
attachments, avatars, and custom emoji all live on the **app** server's
disk (`/srv/ds-chat/uploads`, created in §3a) — a separate machine from
the data server this script runs on — and currently have no backup
mechanism at all. Whatever off-box destination you pick above, include
`/srv/ds-chat/uploads` in it too (e.g. a second `rsync`
line run from the app server).

**Test a restore** (against a scratch database, never directly onto
`ds_chat`):

```bash
sudo -u postgres createdb ds_chat_restore_test
gunzip -c /var/backups/ds-chat/ds-chat-<TIMESTAMP>.sql.gz | sudo -u postgres psql ds_chat_restore_test
sudo -u postgres dropdb ds_chat_restore_test
```

## 8. Troubleshooting

- **`ds-chat` service won't start**: `sudo journalctl -u ds-chat -n 50`.
  Common causes: `/etc/ds-chat/env` missing/malformed (gunicorn workers
  crash-loop on `pydantic-settings` validation errors), or Postgres/Redis
  unreachable (check the data-server firewall rules in §2 actually match
  the app server's real private IP).
- **502/connection refused from NPM**: confirm `curl
  http://127.0.0.1:8000/api/health` works *on the app server itself* first
  (isolates "app is down" from "NPM can't reach it") — then check §3g's
  `ufw` rule matches NPM's actual source IP.
- **Migration fails mid-`upgrade.sh`**: the script stops before restarting
  `ds-chat`, so the previous (still-migrated-to-its-old-schema) code keeps
  running. Fix the migration, re-run the script.
- **Chat works but disconnects after ~a minute of inactivity, then
  reconnects**: expected under the current design (§4's NPM timeout note) —
  not a bug unless it happens mid-typing, in which case raise NPM's proxy
  timeouts.
- **Cert renewal**: handled entirely by NPM's own Let's Encrypt integration
  (not by anything on the app server) — check NPM's own logs if a cert
  expires unexpectedly.

## 9. Known gaps

Carried forward from earlier phases (see `backend/README.md`'s own "Notes /
scope decisions" for the full detail on each):
- No rate limiting on human or bot API traffic.
- No CSRF token (relies on `SameSite=Lax` cookies).
- SSRF protection on outgoing webhooks is creation-time only, not
  re-validated per delivery (DNS-rebinding gap).
- Backup off-box shipping is a placeholder — decide a destination and fill
  in `deploy/backup-postgres.sh`.
- Uploaded chat images, file/video attachments, and custom emoji
  (`/srv/ds-chat/uploads` on the app server) have no backup coverage at
  all yet, on-box or off — see §7.
- Uploaded-but-never-sent images or files (a user attaches one, then never
  hits Send) leak an orphaned file on disk — no cleanup job for this yet.
  Not a security issue (still gated by room membership to view), just an
  eventual disk-space housekeeping item.

None of these are new to this phase — deploying doesn't change any of them,
just makes them reachable from the internet instead of localhost, which is
exactly why they're listed here again rather than only in `backend/README.md`.
