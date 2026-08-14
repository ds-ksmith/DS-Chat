#!/usr/bin/env bash
# Nightly Postgres backup for the KeepItTalking data server.
#
# Install (as root, on the data server):
#   sudo cp deploy/backup-postgres.sh /usr/local/bin/chatapp-backup-postgres.sh
#   sudo chmod 0700 /usr/local/bin/chatapp-backup-postgres.sh
#   sudo crontab -e
#     # add:
#     0 3 * * * /usr/local/bin/chatapp-backup-postgres.sh
#
# See ../DEPLOYMENT.md for the full data-server setup this fits into.

set -euo pipefail

DB_NAME="chatapp"
DB_USER="chatapp"
BACKUP_DIR="/var/backups/chatapp"
RETENTION_DAYS=14
TIMESTAMP="$(date +%F-%H%M%S)"
DEST="${BACKUP_DIR}/chatapp-${TIMESTAMP}.sql.gz"

mkdir -p "$BACKUP_DIR"

# Runs as the postgres OS user (peer auth) so no password handling here --
# see DEPLOYMENT.md for why the crontab entry above is on root's crontab
# calling `sudo -u postgres` implicitly via pg_dump's own permission model.
sudo -u postgres pg_dump --format=plain --no-owner --dbname="$DB_NAME" \
  | gzip > "$DEST"

echo "Backed up ${DB_NAME} to ${DEST}"

# Local rotation -- keep RETENTION_DAYS days on this box regardless of
# whether off-box shipping (below) is configured yet.
find "$BACKUP_DIR" -name 'chatapp-*.sql.gz' -mtime "+${RETENTION_DAYS}" -delete

# --- Off-box shipping -------------------------------------------------
# Not configured yet -- destination wasn't decided as of this script being
# written. Uncomment and fill in ONE of these once you have somewhere to
# send it; a local-only backup doesn't survive losing this machine.
#
# rsync (to a second host reachable by the data server, e.g. over the same
# private network / a WireGuard tunnel used for anything else):
#   rsync -a "$DEST" backup-user@backup-host:/path/to/chatapp-backups/
#
# S3-compatible object storage (needs `aws configure` or rclone set up
# separately first):
#   aws s3 cp "$DEST" s3://your-bucket/chatapp-backups/
#   # or: rclone copy "$DEST" remote:chatapp-backups/
