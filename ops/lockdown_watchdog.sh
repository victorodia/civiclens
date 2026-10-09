#!/bin/bash
# CivicLens nightly lockdown watchdog.
# Runs the full integration suite; retries once to ride out the known
# intermittent publicnode RPC flake on the wallet-balance check. Always
# overwrites lockdown_last_run.log; emails the operator when still red.
set -a; source /home/ubuntu/.watchdog_smtp.env; set +a
OUT=$(python3 /home/ubuntu/lockdown_test.py 2>&1)
if ! echo "$OUT" | grep -q " 0 failed"; then
    sleep 30
    OUT=$(python3 /home/ubuntu/lockdown_test.py 2>&1)
fi
{
    echo "=== $(date -u) ==="
    echo "$OUT" | tail -6
} > /home/ubuntu/lockdown_last_run.log
if ! echo "$OUT" | grep -q " 0 failed"; then
    FAIL_LOG="/home/ubuntu/lockdown_failure_$(date -u +%Y%m%d_%H%M).log"
    echo "$OUT" > "$FAIL_LOG"
    python3 /home/ubuntu/lockdown_notify.py \
        "ALERT: CivicLens lockdown suite FAILED $(date -u +%Y-%m-%d)" \
        "The nightly security suite did not pass after retry.
Full output below; also saved on the server at $FAIL_LOG

$OUT" \
        || echo "NOTIFY_FAILED (check ~/.watchdog_smtp.env)"
fi
