"""
Election-scoping migration (multi-election support).

Idempotent: every step checks current state before acting, so the script can
be re-run safely at any time.

Steps:
  1. Create the new tables (elections, election_polling_units,
     agent_assignments, agent_checkins) if they do not exist.
  2. Create the default "General Election" row (seeded from the legacy
     singleton election_config) if no elections exist.
  3. results: add election_id, backfill to the default election, enforce
     NOT NULL, replace the old single-column unique(pu_id) with the
     per-election unique(pu_id, election_id).
  4. agent_location_pings: add election_id and backfill.
  5. agent_assignments: seed from users.assigned_pu_id (default election).
  6. agent_checkins: seed from users.is_on_site (default election).

Run inside the backend container:
  docker exec civiclens-backend python migrate_elections.py
"""
import asyncio
import sys

from sqlalchemy import text, select
from app.db import engine, Base, AsyncSessionLocal
from app import models  # noqa: F401  (register all tables on Base.metadata)

DEFAULT_ELECTION_ID = "general-election"
DEFAULT_ELECTION_CODE = "GENERAL"


async def _column_exists(conn, table: str, column: str) -> bool:
    row = await conn.execute(text(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name = :t AND column_name = :c"
    ), {"t": table, "c": column})
    return row.first() is not None


async def _constraint_exists(conn, name: str) -> bool:
    row = await conn.execute(text(
        "SELECT 1 FROM pg_constraint WHERE conname = :n"
    ), {"n": name})
    return row.first() is not None


async def _index_exists(conn, name: str) -> bool:
    row = await conn.execute(text(
        "SELECT 1 FROM pg_indexes WHERE indexname = :n"
    ), {"n": name})
    return row.first() is not None


async def main() -> int:
    # 1. New tables (existing tables are untouched by create_all).
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("[MIGRATE] new tables ensured")

    async with AsyncSessionLocal() as db:
        # 2. Default election.
        res = await db.execute(text("SELECT COUNT(*) FROM elections"))
        election_count = res.scalar_one()
        if election_count == 0:
            cfg = await db.execute(text(
                "SELECT election_name, party_a_name, party_b_name, party_c_name "
                "FROM election_config WHERE id = 'global'"
            ))
            cfg_row = cfg.first()
            name = (cfg_row[0] if cfg_row else None) or "General Election"
            pa = (cfg_row[1] if cfg_row else None) or "Party A"
            pb = (cfg_row[2] if cfg_row else None) or "Party B"
            pc = (cfg_row[3] if cfg_row else None) or "Party C"
            await db.execute(text(
                "INSERT INTO elections (id, name, code, type, status, "
                "party_a_name, party_b_name, party_c_name) "
                "VALUES (:id, :name, :code, 'general', 'live', :pa, :pb, :pc)"
            ), {"id": DEFAULT_ELECTION_ID, "name": name,
                "code": DEFAULT_ELECTION_CODE, "pa": pa, "pb": pb, "pc": pc})
            print(f"[MIGRATE] default election created: {name!r}")
        else:
            print(f"[MIGRATE] elections already present ({election_count}), skipping seed")

        # Commit the seed immediately: the DDL below runs on a SECOND
        # connection (engine.begin), and an uncommitted INSERT into elections
        # on this session would block the FK creation on results (self-
        # deadlock across two pooled connections).
        await db.commit()

        # 3. results.election_id
        async with engine.begin() as conn:
            if not await _column_exists(conn, "results", "election_id"):
                await conn.execute(text(
                    "ALTER TABLE results ADD COLUMN election_id VARCHAR(36)"
                ))
                print("[MIGRATE] results.election_id column added")
                await conn.execute(text(
                    "UPDATE results SET election_id = :e WHERE election_id IS NULL"
                ), {"e": DEFAULT_ELECTION_ID})
                await conn.execute(text(
                    "ALTER TABLE results ALTER COLUMN election_id SET NOT NULL"
                ))
                await conn.execute(text(
                    "ALTER TABLE results ADD CONSTRAINT results_elections_fkey "
                    "FOREIGN KEY (election_id) REFERENCES elections(id)"
                ))
                print("[MIGRATE] results.election_id backfilled + NOT NULL + FK")

            # Drop the legacy unique(pu_id) if still present (any auto-name).
            legacy = await conn.execute(text(
                "SELECT conname FROM pg_constraint "
                "WHERE conrelid = 'results'::regclass AND contype = 'u' "
                "AND pg_get_constraintdef(oid) LIKE '%(pu_id)%'"
            ))
            for (cname,) in legacy.fetchall():
                await conn.execute(text(
                    f'ALTER TABLE results DROP CONSTRAINT "{cname}"'
                ))
                print(f"[MIGRATE] dropped legacy unique constraint {cname}")

            if not await _constraint_exists(conn, "uq_result_pu_election"):
                await conn.execute(text(
                    "ALTER TABLE results ADD CONSTRAINT uq_result_pu_election "
                    "UNIQUE (pu_id, election_id)"
                ))
                print("[MIGRATE] added UNIQUE(pu_id, election_id)")
            if not await _index_exists(conn, "ix_results_election_id"):
                await conn.execute(text(
                    "CREATE INDEX ix_results_election_id ON results (election_id)"
                ))
                print("[MIGRATE] added results(election_id) index")

            # 4. agent_location_pings.election_id (nullable; old pings stay valid)
            if not await _column_exists(conn, "agent_location_pings", "election_id"):
                await conn.execute(text(
                    "ALTER TABLE agent_location_pings ADD COLUMN election_id VARCHAR(36)"
                ))
                await conn.execute(text(
                    "UPDATE agent_location_pings SET election_id = :e WHERE election_id IS NULL"
                ), {"e": DEFAULT_ELECTION_ID})
                await conn.execute(text(
                    "ALTER TABLE agent_location_pings ADD CONSTRAINT "
                    "agent_location_pings_elections_fkey FOREIGN KEY (election_id) "
                    "REFERENCES elections(id)"
                ))
                await conn.execute(text(
                    "CREATE INDEX ix_agent_location_pings_election_id "
                    "ON agent_location_pings (election_id)"
                ))
                print("[MIGRATE] pings.election_id added + backfilled + indexed")

        # 5. Seed assignments from users.assigned_pu_id
        seeded = await db.execute(text(
            "INSERT INTO agent_assignments (id, agent_id, election_id, pu_id, created_at) "
            "SELECT gen_random_uuid()::text, u.id, CAST(:e AS varchar), u.assigned_pu_id, NOW() "
            "FROM users u "
            "WHERE u.role = 'agent' AND u.assigned_pu_id IS NOT NULL "
            "AND NOT EXISTS (SELECT 1 FROM agent_assignments a "
            "  WHERE a.agent_id = u.id AND a.election_id = CAST(:e AS varchar) "
            "  AND a.pu_id = u.assigned_pu_id) "
            "ON CONFLICT (election_id, pu_id) DO NOTHING"
        ), {"e": DEFAULT_ELECTION_ID})
        print(f"[MIGRATE] assignments seeded: {seeded.rowcount}")

        # 6. Seed per-election check-ins from the legacy user-row flags
        seeded_ci = await db.execute(text(
            "INSERT INTO agent_checkins (id, agent_id, election_id, pu_id, "
            "checked_in_at, latitude, longitude, is_active) "
            "SELECT gen_random_uuid()::text, u.id, CAST(:e AS varchar), u.assigned_pu_id, "
            "COALESCE(u.last_check_in, NOW()), u.check_in_lat, u.check_in_lng, true "
            "FROM users u "
            "WHERE u.is_on_site = true AND u.assigned_pu_id IS NOT NULL "
            "AND NOT EXISTS (SELECT 1 FROM agent_checkins c "
            "  WHERE c.agent_id = u.id AND c.election_id = CAST(:e AS varchar) AND c.is_active = true)"
        ), {"e": DEFAULT_ELECTION_ID})
        print(f"[MIGRATE] check-ins seeded: {seeded_ci.rowcount}")

        await db.commit()

    await engine.dispose()
    print("[MIGRATE] done")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
