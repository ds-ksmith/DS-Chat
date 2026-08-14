#!/usr/bin/env bash
# Day-2 deploy/upgrade script for the KeepItTalking app server. Run by hand
# over SSH as the `chatapp` user (or via sudo -u chatapp):
#
#   sudo -u chatapp /srv/chatapp/deploy/upgrade.sh
#
# Fails loudly and stops before touching the running service if any step
# fails -- the previous deploy keeps running rather than being torn down
# mid-upgrade. See ../DEPLOYMENT.md for what each step assumes is already
# in place (venv, /etc/chatapp/env, the systemd unit, Node.js).

set -euo pipefail

REPO_DIR="/srv/chatapp"
BACKEND_DIR="${REPO_DIR}/backend"
FRONTEND_DIR="${REPO_DIR}/frontend"
ENV_FILE="/etc/chatapp/env"

echo "==> Pulling latest code"
cd "$REPO_DIR"
git pull --ff-only

echo "==> Installing backend dependencies"
cd "$BACKEND_DIR"
.venv/bin/pip install -e . --quiet

echo "==> Running database migrations"
# alembic reads DATABASE_URL from the environment (backend/alembic/env.py),
# so the env file has to actually be sourced into this shell first -- it's
# not read automatically just because systemd's EnvironmentFile= points at
# it (that only applies to the chatapp.service process, not this script).
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a
.venv/bin/alembic upgrade head

echo "==> Building frontend"
cd "$FRONTEND_DIR"
npm ci --silent
npm run build --silent

echo "==> Restarting chatapp"
# Active WebSocket connections drop here and reconnect automatically within
# a few seconds (frontend/src/ws/useChatSocket.ts's exponential-backoff
# reconnect) -- expected, not a bug, and not worth a blue-green setup for.
sudo systemctl restart chatapp

echo "==> Verifying"
sleep 2
if curl -sf http://127.0.0.1:8000/api/health >/dev/null; then
  echo "Health check OK"
else
  echo "Health check FAILED -- check: sudo journalctl -u chatapp -n 50" >&2
  exit 1
fi
sudo systemctl status chatapp --no-pager -l | head -10

echo "==> Done. journalctl -u chatapp -f to watch logs."
