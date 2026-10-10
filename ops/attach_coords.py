"""Attach scraped INEC GPS coordinates to polling_units.

Maps the CVR site PU id (keyed in inec_coords.jsonl) to our pu_code via the
registry file, then UPDATEs expected_latitude/expected_longitude. Idempotent:
re-running overwrites with the same values. Run inside the backend container:

    PYTHONPATH=/app python3 /tmp/attach_coords.py
"""
import asyncio
import json
import os

import asyncpg

REG = os.environ.get("REGISTRY", "/tmp/inec_registry.jsonl")
COORDS = os.environ.get("COORDS", "/tmp/inec_coords.jsonl")


def state_code(name):
    return name.replace(" ", "")[:3]


async def main():
    # site PU id -> our pu_code
    site2code = {}
    with open(REG, encoding="utf-8") as f:
        for line in f:
            w = json.loads(line)
            if not w["pus"]:
                continue
            s3 = state_code(w["state_name"])
            for p in w["pus"]:
                pcode = p["code"] or str(p["id"])
                site2code[p["id"]] = (
                    f"{s3}-{w['lga_code']}-{w['ward_code']}-{pcode}")
    print(f"registry map: {len(site2code)} site ids", flush=True)

    coords = {}
    n_addr_only = 0
    with open(COORDS, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            if r.get("lat") is None or r.get("lng") is None:
                n_addr_only += 1
                continue
            code = site2code.get(r["pu_id"])
            if code:
                coords[code] = (float(r["lat"]), float(r["lng"]))
    print(f"usable coords: {len(coords)} ({n_addr_only} address-only skipped)",
          flush=True)

    conn = await asyncpg.connect(os.environ["DATABASE_URL"])
    try:
        await conn.execute(
            "CREATE TEMP TABLE c (code text PRIMARY KEY, lat text, lng text)")
        await conn.executemany(
            "INSERT INTO c VALUES ($1,$2,$3)",
            [(k, repr(v[0]), repr(v[1])) for k, v in coords.items()])
        res = await conn.execute(
            "UPDATE polling_units p SET expected_latitude=c.lat, "
            "expected_longitude=c.lng FROM c WHERE p.pu_code=c.code")
        print("update:", res, flush=True)
        got = await conn.fetchval(
            "SELECT count(*) FROM polling_units "
            "WHERE expected_latitude IS NOT NULL")
        total = await conn.fetchval("SELECT count(*) FROM polling_units")
        print(f"PUs with coordinates: {got}/{total}", flush=True)
    finally:
        await conn.close()
    print("ATTACH COMPLETE", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
