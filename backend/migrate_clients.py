"""
Client-tenancy migration.

Gives every election and every user an owning institution (client), so
independent contracting bodies never see each other's people or data.
Platform staff keep client_id NULL and retain cross-client visibility.

Idempotent — safe to re-run.

Steps:
  1. Create the clients table (create_all).
  2. Seed the internal CivicLens client.
  3. elections.client_id: add, backfill, NOT NULL, FK + index.
  4. users.client_id: add, FK + index.
  5. Backfill: every election points at the internal client; agents inherit
     their election's client, everyone else stays NULL (platform admin).

Run inside the backend container:
  docker exec civiclens-backend python migrate_clients.py
"""
import asyncio
import sys

from sqlalchemy import text
from app.db import engine, Base, AsyncSessionLocal
from app import models  # noqa: F401  (register all tables on Base.metadata)

INTERNAL_CLIENT_ID = "civiclens-internal"


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


async def main() -> int:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("[MIGRATE] clients table ensured")

    # DDL first, on its own connection, so the columns exist before any
    # backfill statement references them.
    async with engine.begin() as conn:
        # 3. elections.client_id column + backfill + NOT NULL + FK + index
        if not await _column_exists(conn, "elections", "client_id"):
            await conn.execute(text(
                "ALTER TABLE elections ADD COLUMN client_id VARCHAR(36)"
            ))
            print("[MIGRATE] elections.client_id column added")
        if not await _constraint_exists(conn, "elections_clients_fkey"):
            await conn.execute(text(
                "ALTER TABLE elections ADD CONSTRAINT elections_clients_fkey "
                "FOREIGN KEY (client_id) REFERENCES clients(id)"
            ))
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_elections_client_id "
                "ON elections (client_id)"
            ))
            print("[MIGRATE] elections.client_id FK + index")

        # 4. users.client_id — NULL means platform super-admin
        if not await _column_exists(conn, "users", "client_id"):
            await conn.execute(text(
                "ALTER TABLE users ADD COLUMN client_id VARCHAR(36)"
            ))
        if not await _constraint_exists(conn, "users_clients_fkey"):
            await conn.execute(text(
                "ALTER TABLE users ADD CONSTRAINT users_clients_fkey "
                "FOREIGN KEY (client_id) REFERENCES clients(id)"
            ))
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_users_client_id ON users (client_id)"
            ))
            print("[MIGRATE] users.client_id added")

    # 2 + 3b + 5. Data backfills — one short transaction on a separate
    # session AFTER the DDL has committed, so we never deadlock ourselves.
    async with AsyncSessionLocal() as db:
        res = await db.execute(text("SELECT COUNT(*) FROM clients"))
        if res.scalar_one() == 0:
            await db.execute(text(
                "INSERT INTO clients (id, name, contact_email, notes) "
                "VALUES (:id, 'CivicLens Internal', NULL, "
                "'Default owner for pre-tenancy elections and platform staff work')"
            ), {"id": INTERNAL_CLIENT_ID})
            print("[MIGRATE] internal client created")

        await db.execute(text(
            "UPDATE elections SET client_id = :c WHERE client_id IS NULL"
        ), {"c": INTERNAL_CLIENT_ID})
        # NOT NULL can only be applied once no NULLs remain.
        await db.execute(text(
            "ALTER TABLE elections ALTER COLUMN client_id SET NOT NULL"
        ))
        print("[MIGRATE] elections attached to internal client (NOT NULL)")

        # Agents inherit the client of the election they are assigned to.
        await db.execute(text(
            "UPDATE users u SET client_id = e.client_id "
            "FROM agent_assignments a JOIN elections e ON e.id = a.election_id "
            "WHERE u.id = a.agent_id AND u.role = 'agent' AND u.client_id IS NULL"
        ))
        # Legacy agents with only the PU pointer (no assignment row) predate
        # tenancy; every pre-tenancy election belongs to the internal client.
        await db.execute(text(
            "UPDATE users SET client_id = :c WHERE role = 'agent' "
            "AND client_id IS NULL"
        ), {"c": INTERNAL_CLIENT_ID})
        await db.commit()
        print("[MIGRATE] agent client backfill done")

    await engine.dispose()
    print("[MIGRATE] done")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
