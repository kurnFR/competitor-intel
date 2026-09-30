#!/usr/bin/env bash
# Nightly PostgreSQL backup, keeps 14 days. Example cron:  0 2 * * *  /opt/competitor-intel/deploy/backup.sh
set -euo pipefail
DEST="${BACKUP_DIR:-/var/backups/competitor-intel}"
mkdir -p "$DEST"
STAMP="$(date +%Y%m%d-%H%M%S)"
# Docker Compose deployment:
docker compose -f "$(dirname "$0")/../docker-compose.yml" exec -T db \
  pg_dump -U competitor_intel -Fc competitor_intel > "$DEST/competitor_intel-$STAMP.dump"
chmod 600 "$DEST/competitor_intel-$STAMP.dump"
find "$DEST" -name 'competitor_intel-*.dump' -mtime +14 -delete
echo "Backup written: $DEST/competitor_intel-$STAMP.dump"
# Restore:  docker compose exec -T db pg_restore -U competitor_intel -d competitor_intel --clean < file.dump
