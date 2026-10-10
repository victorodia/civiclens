"""Resume the registry import: geography rows already exist (pass 1 done,
references already remapped). Rebuild the official id sets from the registry
file, delete everything else, restore constraints, verify integrity."""
import asyncio

from sqlalchemy import text

from app.db import AsyncSessionLocal
import import_registry2 as m

ID_TABLES = ("new_state_ids", "new_lga_ids", "new_ward_ids", "new_pu_ids")


async def main():
    async with AsyncSessionLocal() as db:
        await db.execute(text("SET work_mem = '64MB'"))
        for t in ID_TABLES:
            await db.execute(text(f"CREATE TEMP TABLE {t} (id varchar)"))
            await db.execute(text(f"CREATE INDEX ON {t} (id)"))

        # Fill the official id sets by pure computation from the registry.
        n = 0
        for w in m.iter_registry():
            if not w["pus"]:
                continue
            sname = w["state_name"]
            s3 = m.state_code(sname)
            await db.execute(text("INSERT INTO new_state_ids VALUES (:id)"),
                             {"id": m.sid(sname)})
            await db.execute(text("INSERT INTO new_lga_ids VALUES (:id)"),
                             {"id": m.lid(sname, w["lga_code"])})
            await db.execute(text("INSERT INTO new_ward_ids VALUES (:id)"),
                             {"id": m.wid(sname, w["lga_code"], w["ward_code"])})
            batch = []
            for p in w["pus"]:
                pcode, _pname = m.pu_parts(p)
                code = f"{s3}-{w['lga_code']}-{w['ward_code']}-{pcode}"
                batch.append({"id": m.pid(code)})
                if len(batch) >= 5000:
                    await db.execute(text("INSERT INTO new_pu_ids VALUES (:id)"), batch)
                    n += len(batch)
                    batch.clear()
                    print(f"  recorded {n} PU ids...", flush=True)
            if batch:
                await db.execute(text("INSERT INTO new_pu_ids VALUES (:id)"), batch)
                n += len(batch)
        await db.commit()
        print(f"official id sets rebuilt ({n} PUs)", flush=True)

        for t in ID_TABLES:
            await db.execute(text(f"ANALYZE {t}"))

        await db.execute(text(
            "DELETE FROM polling_units WHERE id NOT IN (SELECT id FROM new_pu_ids)"))
        await db.commit()
        print("old PUs deleted", flush=True)
        await db.execute(text(
            "DELETE FROM wards WHERE id NOT IN (SELECT id FROM new_ward_ids)"))
        await db.execute(text(
            "DELETE FROM lgas WHERE id NOT IN (SELECT id FROM new_lga_ids)"))
        await db.execute(text(
            "DELETE FROM states WHERE id NOT IN (SELECT id FROM new_state_ids)"))
        await db.commit()
        print("old geography deleted", flush=True)

        await db.execute(text(
            "ALTER TABLE states ADD CONSTRAINT states_name_key UNIQUE (name)"))
        await db.execute(text(
            "ALTER TABLE states ADD CONSTRAINT states_code_key UNIQUE (code)"))
        await db.execute(text(
            "ALTER TABLE users ADD CONSTRAINT users_assigned_pu_id_fkey "
            "FOREIGN KEY (assigned_pu_id) REFERENCES polling_units(id)"))
        await db.execute(text(
            "ALTER TABLE results ADD CONSTRAINT results_pu_id_fkey "
            "FOREIGN KEY (pu_id) REFERENCES polling_units(id)"))
        await db.commit()
        print("constraints restored", flush=True)

        du = (await db.execute(text(
            "SELECT count(*) FROM users u WHERE u.assigned_pu_id IS NOT NULL "
            "AND NOT EXISTS (SELECT 1 FROM polling_units p WHERE p.id = u.assigned_pu_id)"))).scalar()
        dr = (await db.execute(text(
            "SELECT count(*) FROM results r WHERE NOT EXISTS "
            "(SELECT 1 FROM polling_units p WHERE p.id = r.pu_id)"))).scalar()
        print(f"integrity: dangling user refs={du}, result refs={dr}", flush=True)

    print("IMPORT COMPLETE", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
