#!/bin/bash
# CivicLens nightly audit-chain watchdog.
# Recomputes the WORM audit hash chain read-only; emails the operator on
# failure. Complements the lockdown suite (03:17) with a standalone check.
#
# Paths are env-overridable so the same script runs on the test VM
# (defaults, /home/ubuntu layout) and production (/opt layout via bootstrap).
set -a; source "${CL_WATCHDOG_ENV:-/home/ubuntu/.watchdog_smtp.env}"; set +a

CL_BASE=${CL_BASE:-/home/ubuntu/civiclens}
BACKEND_CONTAINER=${BACKEND_CONTAINER:-civiclens-backend}
LOG=${CL_LOG_DIR:-/home/ubuntu}/audit_chain_last_run.log
NOTIFY=${CL_NOTIFY:-/home/ubuntu/lockdown_notify.py}

sudo docker cp "$CL_BASE/ops/audit_chain_check.py" "$BACKEND_CONTAINER:/tmp/audit_chain_check.py" >/dev/null 2>&1
OUT=$(sudo docker exec "$BACKEND_CONTAINER" python3 /tmp/audit_chain_check.py 2>&1)
RC=$?

{
    echo "=== $(date -u) ==="
    echo "$OUT"
} > "$LOG"

if [ $RC -ne 0 ]; then
    python3 "$NOTIFY" \
        "ALERT: CivicLens audit chain INVALID $(date -u +%Y-%m-%d)" \
        "The nightly audit-chain check failed — the WORM log's hash linkage
is broken (rows inserted, reordered, deleted, or content altered).

$OUT

Last run log: $LOG" \
        || echo "NOTIFY_FAILED (check watchdog SMTP env)" >> "$LOG"
fi
exit $RC
