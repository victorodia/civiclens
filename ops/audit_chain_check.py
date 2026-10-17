#!/usr/bin/env python3
"""Read-only CivicLens audit-chain verification (watchdog edition).

Mirrors the platform-scope check of GET /admin/audit-logs/verify without
needing an admin JWT: recomputes every chained row's row_hash from its
stored fields and verifies prev_hash linkage back to the genesis hash.

Run inside the backend container:
    docker cp ops/audit_chain_check.py civiclens-backend:/tmp/ && \
    docker exec civiclens-backend python3 /tmp/audit_chain_check.py

Exit code 0 = chain valid; 1 = break detected (details on stdout).
Read-only: never writes to the database.
"""
import asyncio
import hashlib
import os
import sys

sys.path.insert(0, "/app")

import asyncpg

from app.security import AUDIT_GENESIS_HASH, audit_canonical


async def main() -> int:
    url = os.environ["DATABASE_URL"].replace("postgresql+asyncpg://",
                                             "postgresql://")
    conn = await asyncpg.connect(url)
    try:
        rows = await conn.fetch(
            'SELECT seq, "timestamp", actor_id, actor_role, tenant_id, '
            "action_type, target_type, target_entity_id, election_id, "
            "details, ip_address, device_fingerprint, prev_hash, row_hash "
            "FROM audit_logs WHERE row_hash IS NOT NULL ORDER BY seq ASC")
    finally:
        await conn.close()

    expected_prev = AUDIT_GENESIS_HASH
    checked = 0
    for r in rows:
        recomputed = hashlib.sha256(audit_canonical(
            r["seq"], r["timestamp"], r["actor_id"], r["actor_role"],
            r["tenant_id"], r["action_type"], r["target_type"],
            r["target_entity_id"], r["election_id"], r["details"],
            r["ip_address"], r["device_fingerprint"],
            r["prev_hash"]).encode()).hexdigest()
        if recomputed != r["row_hash"]:
            print(f"INVALID content altered at seq={r['seq']} "
                  f"(row_hash mismatch)")
            print(f"rows_checked={checked}")
            return 1
        if (r["prev_hash"] or AUDIT_GENESIS_HASH) != expected_prev:
            print(f"INVALID prev_hash linkage broken at seq={r['seq']} "
                  f"(row inserted, reordered or deleted)")
            print(f"rows_checked={checked}")
            return 1
        expected_prev = r["row_hash"]
        checked += 1
    print(f"VALID rows_checked={checked}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
