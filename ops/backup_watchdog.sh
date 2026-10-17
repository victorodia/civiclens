#!/bin/bash
# CivicLens nightly backup watchdog.
# Dumps the PostgreSQL database and evidence-uploads directory, verifies
# each archive (exit code, gzip integrity, minimum size), prunes old
# nightlies, and emails the operator on any failure.
#
# Paths are env-overridable so the same script runs on the test VM
# (defaults, /home/ubuntu layout) and production (/opt layout via bootstrap).
set -a; source "${CL_WATCHDOG_ENV:-/home/ubuntu/.watchdog_smtp.env}"; set +a

BACKUP_DIR=${CL_BACKUP:-/home/ubuntu/backups/nightly}
UPLOADS=${CL_DATA:-/home/ubuntu/civiclens-data/uploads}
DB_CONTAINER=${DB_CONTAINER:-civiclens-db}
NOTIFY=${CL_NOTIFY:-/home/ubuntu/lockdown_notify.py}
LOG=${CL_LOG_DIR:-/home/ubuntu}/backup_last_run.log
RETENTION_DAYS=14
DB_MIN_BYTES=500000      # floor: baseline dump was ~1.5 MB; alert if smaller
UP_MIN_BYTES=1000        # floor for the uploads tar (empty dir still > 1 KB)

STAMP=$(date -u +%Y%m%d)
mkdir -p "$BACKUP_DIR"

ERRORS=""

log() { echo "[$(date -u +%H:%M:%S)] $*"; }

# 1) Database dump
DB_FILE="$BACKUP_DIR/civiclens_db_$STAMP.sql.gz"
if sudo docker exec "$DB_CONTAINER" pg_dump -U civiclens_user -d civiclens --no-owner 2>>"$LOG" | gzip > "$DB_FILE"; then
    if gzip -t "$DB_FILE" 2>>"$LOG"; then
        SIZE=$(stat -c%s "$DB_FILE")
        if [ "$SIZE" -lt $DB_MIN_BYTES ]; then
            ERRORS="$ERRORS\nDB dump suspiciously small: $SIZE bytes ($DB_FILE)"
        fi
        log "db dump ok: $DB_FILE ($SIZE bytes)"
    else
        ERRORS="$ERRORS\nDB dump gzip integrity failed: $DB_FILE"
    fi
else
    ERRORS="$ERRORS\npg_dump failed (see $LOG)"
fi

# 2) Evidence uploads
UP_FILE="$BACKUP_DIR/civiclens_uploads_$STAMP.tar.gz"
if tar -czf "$UP_FILE" -C "$(dirname "$UPLOADS")" "$(basename "$UPLOADS")" 2>>"$LOG"; then
    if gzip -t "$UP_FILE" 2>>"$LOG"; then
        SIZE=$(stat -c%s "$UP_FILE")
        if [ "$SIZE" -lt $UP_MIN_BYTES ]; then
            ERRORS="$ERRORS\nUploads archive suspiciously small: $SIZE bytes ($UP_FILE)"
        fi
        log "uploads archive ok: $UP_FILE ($SIZE bytes)"
    else
        ERRORS="$ERRORS\nUploads gzip integrity failed: $UP_FILE"
    fi
else
    ERRORS="$ERRORS\ntar of $UPLOADS failed (see $LOG)"
fi

# 3) Prune nightlies older than retention
PRUNED=$(find "$BACKUP_DIR" -name 'civiclens_*.gz' -mtime +$RETENTION_DAYS -delete -print | wc -l)
log "pruned $PRUNED archive(s) older than $RETENTION_DAYS days"

{
    echo "=== $(date -u) ==="
    echo -e "$ERRORS"
} >> "$LOG"

if [ -n "$ERRORS" ]; then
    python3 "$NOTIFY" \
        "ALERT: CivicLens backup FAILED $(date -u +%Y-%m-%d)" \
        "The nightly backup watchdog reported problems:

$(echo -e "$ERRORS")

Log: $LOG
Backup dir: $BACKUP_DIR" \
        >> "$LOG" 2>&1 || echo "NOTIFY_FAILED (check watchdog SMTP env)" >> "$LOG"
    exit 1
fi
exit 0
