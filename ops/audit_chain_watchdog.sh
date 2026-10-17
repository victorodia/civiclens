#!/bin/bash
# CivicLens nightly audit-chain watchdog.
# Recomputes the WORM audit hash chain read-only; emails the operator on
# failure. Complements the lockdown suite (03:17) with a standalone check.
set -a; source /home/ubuntu/.watchdog_smtp.env; set +a

REPO=/home/ubuntu/civiclens
sudo docker cp "$REPO/ops/audit_chain_check.py" civiclens-backend:/tmp/audit_chain_check.py >/dev/null 2>&1
OUT=$(sudo docker exec civiclens-backend python3 /tmp/audit_chain_check.py 2>&1)
RC=$?

{
    echo "=== $(date -u) ==="
    echo "$OUT"
} > /home/ubuntu/audit_chain_last_run.log

if [ $RC -ne 0 ]; then
    python3 /home/ubuntu/lockdown_notify.py \
        "ALERT: CivicLens audit chain INVALID $(date -u +%Y-%m-%d)" \
        "The nightly audit-chain check failed — the WORM log's hash linkage
is broken (rows inserted, reordered, deleted, or content altered).

$OUT

Last run log: /home/ubuntu/audit_chain_last_run.log" \
        || echo "NOTIFY_FAILED (check ~/.watchdog_smtp.env)"
fi
exit $RC
