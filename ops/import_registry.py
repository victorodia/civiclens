#!/usr/bin/env python3
"""
Import the full INEC registry (scraped from cvr.inecnigeria.org) into the
CivicLens database, replacing the synthetic demo geography.

Memory-light design for the 1GB VM: streams the registry file twice with
plain dicts and SQLAlchemy Core executemany inserts — never builds the
176k-row ORM object graph that thrashed this box.

Flow:
  pass 0: verify code uniqueness and that every referenced user/result PU
          resolves to an official row (aborts before any write otherwise)
  pass 1: stream-insert new geography beside the old rows
  then:   remap users.assigned_pu_id / results.pu_id, delete old rows

Run inside the backend container:
    docker cp inec_registry.jsonl civiclens-backend:/tmp/
    docker cp import_registry2.py  civiclens-backend:/tmp/
    docker exec -d civiclens-backend sh -c \
        "PYTHONPATH=/app python3 -u /tmp/import_registry2.py > /tmp/import2.log 2>&1"
"""
import asyncio
import json
import re
import sys
import unicodedata
import uuid

from sqlalchemy import insert, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db import AsyncSessionLocal
from app.models import State, LGA, Ward, PollingUnit

REG = "/tmp/inec_registry.jsonl"
NS = uuid.NAMESPACE_URL


def norm(s):
    if s is None:
        return ""
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    s = s.upper()
    s = re.sub(r"[^A-Z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


# INEC labels mostly use " - " but 351 PU labels use unicode dashes (–, —, −)
LABEL_RE = re.compile(r"^\s*(\d+)\s*[\-–—−]\s*(.+?)\s*$")


def split_label(label):
    """'01 - AGUATA' -> ('01', 'AGUATA'); ('', label) if no numeric prefix."""
    m = LABEL_RE.match(str(label))
    if m:
        return m.group(1), re.sub(r"\s+", " ", m.group(2)).strip()
    return "", re.sub(r"\s+", " ", str(label)).strip()


def pu_parts(p):
    """(code, name) for a scraped PU; recovers the code from the label when
    the scraper's ASCII-only split missed a unicode dash (351 labels)."""
    if p["code"]:
        return p["code"], p["name"]
    m = LABEL_RE.match(p["name"])
    if m:
        return m.group(1), re.sub(r"\s+", " ", m.group(2)).strip()
    return str(p["id"]), p["name"]  # last resort: site id keeps the code unique


ROMAN_SUFFIX = re.compile(
    r"\s+(I{1,3}|IV|V|VI{0,3}|IX|X|[1-9])$")


def norm_base(s):
    """norm() with any trailing split-unit numeral removed: the old synthetic
    registry has one row per location where INEC now splits into I/II/III."""
    return ROMAN_SUFFIX.sub("", norm(s))


# our legacy registry called the Federal Capital Territory "ABUJA"
STATE_ALIAS = {"ABUJA": "FCT"}


def norm_state(s):
    n = norm(s)
    return STATE_ALIAS.get(n, n)


def state_code(name):
    return name.replace(" ", "")[:3]


def sid(sname):
    return str(uuid.uuid5(NS, f"https://civiclens.io/state/{sname}"))


def lid(sname, lga_code):
    return str(uuid.uuid5(NS, f"https://civiclens.io/lga/{state_code(sname)}/{lga_code}"))


def wid(sname, lga_code, ward_code):
    return str(uuid.uuid5(NS, f"https://civiclens.io/ward/{state_code(sname)}/{lga_code}/{ward_code}"))


def pid(pu_code):
    return str(uuid.uuid5(NS, f"https://civiclens.io/pu/{pu_code}"))


def iter_registry():
    with open(REG, encoding="utf-8") as f:
        for line in f:
            yield json.loads(line)


async def main():
    # ---------- capture current references ----------
    async with AsyncSessionLocal() as db:
        refs = []  # (kind, owner_id, key4)
        res = await db.execute(text(
            "SELECT 'user', u.email::text, pu.name, w.name, l.name, s.name "
            "FROM users u JOIN polling_units pu ON pu.id = u.assigned_pu_id "
            "JOIN wards w ON w.id = pu.ward_id JOIN lgas l ON l.id = w.lga_id "
            "JOIN states s ON s.id = l.state_id WHERE u.assigned_pu_id IS NOT NULL"))
        for kind, owner, pn, wn, ln, sn in res.all():
            refs.append((kind, owner, (norm(pn), norm(wn), norm(ln), norm_state(sn))))
        res = await db.execute(text(
            "SELECT 'result', r.id::text, pu.name, w.name, l.name, s.name "
            "FROM results r JOIN polling_units pu ON pu.id = r.pu_id "
            "JOIN wards w ON w.id = pu.ward_id JOIN lgas l ON l.id = w.lga_id "
            "JOIN states s ON s.id = l.state_id"))
        for kind, owner, pn, wn, ln, sn in res.all():
            refs.append((kind, owner, (norm(pn), norm(wn), norm(ln), norm_state(sn))))
        print(f"referenced PUs to remap: {len(refs)}", flush=True)

        ref_keys = {k4 for _, _, k4 in refs}

    # ---------- pass 0: uniqueness + reference resolution ----------
    seen_codes = set()
    seen_ward_keys = {}
    ghosts = []
    ref_hits = {}   # key4 -> pu_code
    ref_hits3 = {}  # (pu, lga, state) -> pu_code  (fallback, first wins)
    ref_hitsR = {}  # (pu-base, lga, state) -> pu_code (split-unit fallback)
    collisions = []
    n_states, n_lgas, n_wards, n_pus = set(), set(), set(), 0

    for w in iter_registry():
        sname = w["state_name"]
        s3 = state_code(sname)
        n_states.add(sname)
        n_lgas.add((sname, w["lga_code"]))
        if not w["pus"]:
            ghosts.append(f"{sname}/{w['lga_name']}/{w['ward_name']}")
            continue
        n_wards.add((sname, w["lga_code"], w["ward_code"]))
        wkey = (s3, w["lga_code"], w["ward_code"])
        if wkey in seen_ward_keys and seen_ward_keys[wkey] != w["ward_name"]:
            collisions.append(f"ward code {wkey} reused: {seen_ward_keys[wkey]} vs {w['ward_name']}")
        seen_ward_keys[wkey] = w["ward_name"]
        for p in w["pus"]:
            pcode, pname = pu_parts(p)
            code = f"{s3}-{w['lga_code']}-{w['ward_code']}-{pcode}"
            if code in seen_codes:
                collisions.append(f"PU code {code} duplicate")
            seen_codes.add(code)
            n_pus += 1
            k4 = (norm(pname), norm(w["ward_name"]), norm(w["lga_name"]), norm_state(sname))
            if k4 in ref_keys and k4 not in ref_hits:
                ref_hits[k4] = code
            k3 = (k4[0], k4[2], k4[3])
            if k3 not in ref_hits3:
                ref_hits3[k3] = code
            kR = (norm_base(pname), k4[2], k4[3])
            if kR not in ref_hitsR:
                ref_hitsR[kR] = code

    print(f"registry: {len(n_states)} states, {len(n_lgas)} LGAs, "
          f"{len(n_wards)} wards, {n_pus} PUs; ghost wards skipped: {ghosts}",
          flush=True)
    if collisions:
        print("COLLISIONS — aborting, nothing changed:", flush=True)
        for c in collisions[:20]:
            print("  ", c, flush=True)
        sys.exit(1)

    misses = []
    for kind, owner, k4 in refs:
        if k4 not in ref_hits and k4 not in ref_hits3 \
                and (norm_base(k4[0]), k4[2], k4[3]) not in ref_hitsR:
            misses.append(f"{kind} {owner}: {k4}")
    if misses:
        print("REMAP MISSES — aborting, nothing changed:", flush=True)
        for m in misses:
            print("  ", m, flush=True)
        sys.exit(1)
    print("all referenced PUs resolve to official rows", flush=True)

    # Old seed rows hold states' unique name/code constraints; dropping them
    # for the duration of the import lets deterministic-id rows insert while
    # same-named old rows still exist. Re-added after cleanup below.
    async with AsyncSessionLocal() as db:
        await db.execute(text(
            "ALTER TABLE states DROP CONSTRAINT IF EXISTS states_name_key"))
        await db.execute(text(
            "ALTER TABLE states DROP CONSTRAINT IF EXISTS states_code_key"))
        # App-created PU rows (e.g. e2e test units) may already hold an
        # official pu_code under a random id; pass 1 re-ids them onto the
        # deterministic id via ON CONFLICT (pu_code) DO UPDATE, which needs
        # these FKs out of the way. Restored verbatim after cleanup.
        await db.execute(text(
            "ALTER TABLE users DROP CONSTRAINT IF EXISTS users_assigned_pu_id_fkey"))
        await db.execute(text(
            "ALTER TABLE results DROP CONSTRAINT IF EXISTS results_pu_id_fkey"))
        await db.commit()

    # ---------- pass 1: stream-insert new geography (rerun-safe) ----------
    async with AsyncSessionLocal() as db:
        # New-row id sets: everything NOT in these temp tables at the end is
        # an old row and gets deleted. Ids are recorded for EVERY registry
        # row seen, so reruns converge even after a partial previous run.
        await db.execute(text("CREATE TEMP TABLE new_state_ids (id varchar)"))
        await db.execute(text("CREATE TEMP TABLE new_lga_ids (id varchar)"))
        await db.execute(text("CREATE TEMP TABLE new_ward_ids (id varchar)"))
        await db.execute(text("CREATE TEMP TABLE new_pu_ids (id varchar)"))
        # The 176k-row anti-join hash needs more than the 4MB default
        # work_mem, else the planner falls back to a nested-loop seqscan
        # (measured: never finishes on this VM).
        await db.execute(text("SET work_mem = '64MB'"))
        # Indexes + stats for the cleanup deletes.
        for _t in ("new_state_ids", "new_lga_ids", "new_ward_ids", "new_pu_ids"):
            await db.execute(text(f"CREATE INDEX ON {_t} (id)"))
            await db.execute(text(f"ANALYZE {_t}"))

        # Preload existing deterministic ids (partial leftovers from a killed
        # run). Guard by id, not name: old rows may share a name (e.g. an old
        # "ANAMBRA" with a random uuid) while children FK-reference sid(name).
        existing_state_ids = {r for (r,) in (await db.execute(text("SELECT id FROM states"))).all()}
        existing_lga_ids = {r for (r,) in (await db.execute(text("SELECT id FROM lgas"))).all()}
        existing_ward_ids = {r for (r,) in (await db.execute(text("SELECT id FROM wards"))).all()}

        inserted_states = set(existing_state_ids)
        inserted_lgas = set(existing_lga_ids)
        inserted_wards = set(existing_ward_ids)
        batch = []
        batch_ids = []
        n = 0

        async def flush():
            nonlocal batch, batch_ids, n
            if batch:
                # ON CONFLICT (pu_code) DO UPDATE re-ids app-created rows
                # holding an official code under a random uuid, and re-parents
                # them onto the new ward (else the old-ward cleanup delete
                # hits a FK from the surviving PU row).
                pu_stmt = pg_insert(PollingUnit.__table__)
                pu_stmt = pu_stmt.on_conflict_do_update(
                    index_elements=["pu_code"],
                    set_={"id": pu_stmt.excluded.id,
                          "ward_id": pu_stmt.excluded.ward_id,
                          "name": pu_stmt.excluded.name})
                await db.execute(pu_stmt, batch)
                await db.execute(text("INSERT INTO new_pu_ids VALUES (:id)"),
                                 batch_ids)
                n += len(batch)
                print(f"  processed {n} PUs...", flush=True)
                batch, batch_ids = [], []
                await db.commit()

        for w in iter_registry():
            sname = w["state_name"]
            s3 = state_code(sname)
            if not w["pus"]:
                continue
            if sid(sname) not in inserted_states:
                await db.execute(
                    pg_insert(State.__table__).on_conflict_do_nothing(),
                    {"id": sid(sname), "name": sname, "code": s3})
                await db.execute(text("INSERT INTO new_state_ids VALUES (:id)"),
                                 {"id": sid(sname)})
                inserted_states.add(sid(sname))
            lkey = (sname, w["lga_code"])
            if lid(*lkey) not in inserted_lgas:
                await db.execute(
                    pg_insert(LGA.__table__).on_conflict_do_nothing(), {
                    "id": lid(*lkey), "name": w["lga_name"],
                    "state_id": sid(sname)})
                await db.execute(text("INSERT INTO new_lga_ids VALUES (:id)"),
                                 {"id": lid(*lkey)})
                inserted_lgas.add(lid(*lkey))
            wkey = (sname, w["lga_code"], w["ward_code"])
            if wid(*wkey) not in inserted_wards:
                await db.execute(
                    pg_insert(Ward.__table__).on_conflict_do_nothing(), {
                    "id": wid(*wkey), "name": w["ward_name"],
                    "lga_id": lid(sname, w["lga_code"])})
                await db.execute(text("INSERT INTO new_ward_ids VALUES (:id)"),
                                 {"id": wid(*wkey)})
                inserted_wards.add(wid(*wkey))
            ward_id = wid(*wkey)
            for p in w["pus"]:
                pcode, pname = pu_parts(p)
                code = f"{s3}-{w['lga_code']}-{w['ward_code']}-{pcode}"
                new_id = pid(code)
                batch.append({"id": new_id, "pu_code": code,
                              "name": pname, "ward_id": ward_id})
                batch_ids.append({"id": new_id})
            if len(batch) >= 2000:
                await flush()
        await flush()
        print(f"geography converged: {len(inserted_states)} states, "
              f"{len(inserted_lgas)} LGAs, {len(inserted_wards)} wards, "
              f"{n} PUs processed", flush=True)

        # ---------- remap references ----------
        for kind, owner, k4 in refs:
            code = (ref_hits.get(k4)
                    or ref_hits3.get((k4[0], k4[2], k4[3]))
                    or ref_hitsR[(norm_base(k4[0]), k4[2], k4[3])])
            new_id = pid(code)
            if kind == "user":
                await db.execute(text(
                    "UPDATE users SET assigned_pu_id = :nid WHERE email = :o"),
                    {"nid": new_id, "o": owner})
            else:
                await db.execute(text(
                    "UPDATE results SET pu_id = :nid WHERE id = :o"),
                    {"nid": new_id, "o": owner})
        await db.commit()
        print(f"remapped {len(refs)} references", flush=True)

        # Refresh temp-table stats after the bulk fill so the planner picks
        # indexed anti-joins for the cleanup deletes below.
        for _t in ("new_state_ids", "new_lga_ids", "new_ward_ids", "new_pu_ids"):
            await db.execute(text(f"ANALYZE {_t}"))

        # ---------- delete every row not in the new id sets ----------
        # Safe now: users/results point at new rows; everything else left is
        # an old row (or partial leftover) that nothing references.
        await db.execute(text(
            "DELETE FROM polling_units WHERE id NOT IN (SELECT id FROM new_pu_ids)"))
        await db.execute(text(
            "DELETE FROM wards WHERE id NOT IN (SELECT id FROM new_ward_ids)"))
        await db.execute(text(
            "DELETE FROM lgas WHERE id NOT IN (SELECT id FROM new_lga_ids)"))
        await db.execute(text(
            "DELETE FROM states WHERE id NOT IN (SELECT id FROM new_state_ids)"))
        await db.commit()
        print("old geography deleted", flush=True)

        # Restore the unique constraints now that duplicates are gone.
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
        print("state constraints restored", flush=True)

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
