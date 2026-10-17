#!/bin/bash
# CivicLens nightly lockdown watchdog.
# Runs the full integration suite; retries once to ride out the known
# intermittent publicnode RPC flake on the wallet-balance check. Always
# overwrites the last-run log; emails the operator when still red.
#
# Paths are env-overridable so the same script runs on the test VM
# (defaults, /home/ubuntu layout) and production (/opt layout via bootstrap).
set -a; source "${CL_WATCHDOG_ENV:-/home/ubuntu/.watchdog_smtp.env}"; set +a

CL_BASE=${CL_BASE:-/home/ubuntu/civiclens}
SUITE=${CL_SUITE:-$CL_BASE/ops/lockdown_test.py}
NOTIFY=${CL_NOTIFY:-/home/ubuntu/lockdown_notify.py}
LOG_DIR=${CL_LOG_DIR:-/home/ubuntu}

OUT=$(python3 "$SUITE" 2>&1)
if ! echo "$OUT" | grep -q " 0 failed"; then
    sleep 30
    OUT=$(python3 "$SUITE" 2>&1)
fi
{
    echo "=== $(date -u) ==="
    echo "$OUT" | tail -6
} > "$LOG_DIR/lockdown_last_run.log"
if ! echo "$OUT" | grep -q " 0 failed"; then
    FAIL_LOG="$LOG_DIR/lockdown_failure_$(date -u +%Y%m%d_%H%M).log"
    echo "$OUT" > "$FAIL_LOG"
    python3 "$NOTIFY" \
        "ALERT: CivicLens lockdown suite FAILED $(date -u +%Y-%m-%d)" \
        "The nightly security suite did not pass after retry.
Full output below; also saved on the server at $FAIL_LOG

$OUT" \
        || echo "NOTIFY_FAILED (check watchdog SMTP env)"
fi
