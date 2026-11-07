#!/usr/bin/env bash
# Day-2 deploy/upgrade script for the DS Chat app server. Run by hand
# over SSH as the `ds-chat` user (or via sudo -u ds-chat):
#
#   sudo -u ds-chat /srv/ds-chat/deploy/upgrade.sh
#
# Fails loudly and stops before touching the running service if any step
# fails -- the previous deploy keeps running rather than being torn down
# mid-upgrade. See ../DEPLOYMENT.md for what each step assumes is already
# in place (venv, /etc/ds-chat/env, the systemd unit, Node.js).

set -euo pipefail

REPO_DIR="/srv/ds-chat"
BACKEND_DIR="${REPO_DIR}/backend"
FRONTEND_DIR="${REPO_DIR}/frontend"
ENV_FILE="/etc/ds-chat/env"

echo "==> Fetching latest release"
cd "$REPO_DIR"
git fetch --tags --force
LATEST_TAG="$(git tag --sort=-creatordate | head -n1)"
if [[ -z "$LATEST_TAG" ]]; then
  echo "No tags found -- nothing to deploy" >&2
  exit 1
fi
echo "Deploying $LATEST_TAG"
# Detached HEAD, not a branch checkout -- this directory only ever runs a
# tagged release, never whatever the default branch's tip happens to be.
git checkout --quiet --detach "$LATEST_TAG"

echo "==> Installing backend dependencies"
cd "$BACKEND_DIR"
.venv/bin/pip install -e . --quiet

echo "==> Running database migrations"
# alembic reads DATABASE_URL from the environment (backend/alembic/env.py),
# so the env file has to actually be sourced into this shell first -- it's
# not read automatically just because systemd's EnvironmentFile= points at
# it (that only applies to the ds-chat.service process, not this script).
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a
.venv/bin/alembic upgrade head

echo "==> Building frontend"
cd "$FRONTEND_DIR"
npm ci --silent
npm run build --silent

echo "==> Restarting ds-chat"
# Active WebSocket connections drop here and reconnect automatically within
# a few seconds (frontend/src/ws/useChatSocket.ts's exponential-backoff
# reconnect) -- expected, not a bug, and not worth a blue-green setup for.
sudo systemctl restart ds-chat

echo "==> Verifying"
# Retried rather than checked once after a fixed sleep: the service runs
# several workers that each import the app and run startup work, which can
# take longer than a couple of seconds, so a single early check reported
# failure on deploys that were in fact healthy a moment later.
HEALTH_URL="http://127.0.0.1:8000/api/health"
HEALTH_TIMEOUT_SECONDS=30
healthy=false
for ((waited = 0; waited < HEALTH_TIMEOUT_SECONDS; waited += 2)); do
  sleep 2
  if curl -sf "$HEALTH_URL" >/dev/null; then
    healthy=true
    break
  fi
done
if [[ "$healthy" == true ]]; then
  echo "Health check OK (after ~$((waited + 2))s)"
else
  echo "Health check FAILED after ${HEALTH_TIMEOUT_SECONDS}s -- check: sudo journalctl -u ds-chat -n 50" >&2
  exit 1
fi
sudo systemctl status ds-chat --no-pager -l | head -10

echo "==> Done. journalctl -u ds-chat -f to watch logs."
