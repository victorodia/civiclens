"""Live multi-institution field drill.

Builds the user's 4-institution scenario through the REAL API paths:
  Mission Alpha  -> Presidential I    (APC, ADC, NDC)     2 LGAs (Lagos, Kano)
  Mission Beta   -> Delta Senatorial  (APM, AAC, PDP)     all Delta LGAs
  Mission Gamma  -> Osun Gubernatorial (ACCORD, PDP, NDC) all Osun LGAs
  Mission Delta  -> Presidential II   (ACCORD, AAC, BOOT) 2 LGAs (Rivers, FCT)

For each: client row, client-admin account, election under that client
(created BY the client admin, so the forced-own-client path is exercised),
scope, live status, and one agent provisioned by the client admin.

Run:  docker exec civiclens-backend sh -c 'PYTHONPATH=/app python /tmp/drill_setup.py'
Idempotent-ish: refuses to run if DRILL-PRES-A already exists.
"""
import asyncio
import json
import urllib.request
import urllib.error

BASE = "http://localhost:8001"
PLAT_PASS = "Drill#Platform2026x"
ADM_PASS = "Drill#Admin2026x"

def http(method, path, body=None, token=None):
    req = urllib.request.Request(BASE + path, method=method)
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, data=data, timeout=60) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or "{}")
        except Exception:
            return e.code, {}

PLAN = [
    {"key": "alpha", "client": "Drill Mission Alpha (Presidential I)",
     "admin": "drill.adm.alpha@civiclens.io", "agent": "drill.agent.alpha@civiclens.io",
     "election": {"name": "Presidential Election — Drill A", "code": "DRILL-PRES-A",
                  "type": "presidential", "party_a_name": "APC", "party_b_name": "ADC", "party_c_name": "NDC"},
     "states": ["LAGOS", "KANO"]},
    {"key": "beta", "client": "Drill Mission Beta (Delta Senatorial)",
     "admin": "drill.adm.beta@civiclens.io", "agent": "drill.agent.beta@civiclens.io",
     "election": {"name": "Delta Senatorial Election — Drill", "code": "DRILL-DEL-SEN",
                  "type": "senatorial", "party_a_name": "APM", "party_b_name": "AAC", "party_c_name": "PDP"},
     "states": ["DELTA"]},
    {"key": "gamma", "client": "Drill Mission Gamma (Osun Gubernatorial)",
     "admin": "drill.adm.gamma@civiclens.io", "agent": "drill.agent.gamma@civiclens.io",
     "election": {"name": "Osun Gubernatorial Election — Drill", "code": "DRILL-OSU-GOV",
                  "type": "gubernatorial", "party_a_name": "ACCORD", "party_b_name": "PDP", "party_c_name": "NDC"},
     "states": ["OSUN"]},
    {"key": "delta", "client": "Drill Mission Delta (Presidential II)",
     "admin": "drill.adm.delta@civiclens.io", "agent": "drill.agent.delta@civiclens.io",
     "election": {"name": "Presidential Election — Drill B", "code": "DRILL-PRES-B",
                  "type": "presidential", "party_a_name": "ACCORD", "party_b_name": "AAC", "party_c_name": "BOOT"},
     "states": ["RIVERS", "FCT"]},
]

async def main():
    from app.db import AsyncSessionLocal
    from app.security import get_password_hash
    from sqlalchemy import text

    async with AsyncSessionLocal() as db:
        clash = (await db.execute(text(
            "SELECT 1 FROM elections WHERE code LIKE 'DRILL-%' LIMIT 1"))).first()
        if clash:
            print("DRILL elections already exist — aborting (clean up first).")
            return
        # Platform drill admin
        await db.execute(text(
            "INSERT INTO users (id, email, hashed_password, full_name, role, is_active, requires_password_reset) "
            "VALUES ('drill-platform', 'drill.platform@civiclens.io', :h, 'Drill Platform Admin', 'admin', true, false) "
            "ON CONFLICT (id) DO NOTHING"), {"h": get_password_hash(PLAT_PASS)})
        # Resolve LGA ids per planned state
        lga_map = {}
        for p in PLAN:
            ids = []
            for sname in p["states"]:
                rows = (await db.execute(text(
                    "SELECT l.id FROM lgas l JOIN states s ON s.id = l.state_id "
                    "WHERE s.name = :n"), {"n": sname})).all()
                if not rows:
                    print(f"!! state not found: {sname}")
                    continue
                if sname in ("DELTA", "OSUN"):
                    ids.extend(r[0] for r in rows)          # whole state
                else:
                    ids.append(rows[0][0])                  # one LGA is enough for a drill
            lga_map[p["key"]] = ids
        await db.commit()

    s, d = http("POST", "/auth/login", {"email": "drill.platform@civiclens.io", "password": PLAT_PASS})
    plat = d.get("access_token")
    assert plat, f"platform login failed: {s} {d}"

    out = {"platform": {"email": "drill.platform@civiclens.io", "password": PLAT_PASS}, "missions": []}

    # Pre-create clients as platform, then client admins in DB
    client_ids = {}
    for p in PLAN:
        s, c = http("POST", "/admin/clients", {"name": p["client"], "notes": "Live drill — safe to delete"}, token=plat)
        assert s == 201, f"client create failed: {s} {c}"
        client_ids[p["key"]] = c["id"]

    async with AsyncSessionLocal() as db:
        for p in PLAN:
            await db.execute(text(
                "INSERT INTO users (id, email, hashed_password, full_name, role, is_active, "
                "requires_password_reset, client_id) VALUES (:id, :e, :h, :fn, 'admin', true, false, :c)"),
                {"id": f"drill-adm-{p['key']}", "e": p["admin"], "fn": f"Drill Admin {p['key']}",
                 "h": get_password_hash(ADM_PASS), "c": client_ids[p["key"]]})
        await db.commit()

    for p in PLAN:
        # Client admin logs in and creates THEIR election (own client forced)
        s, d = http("POST", "/auth/login", {"email": p["admin"], "password": ADM_PASS})
        tok = d.get("access_token")
        assert tok, f"admin login failed {p['key']}: {s} {d}"
        s, e = http("POST", "/admin/elections", p["election"], token=tok)
        assert s == 201, f"election create failed {p['key']}: {s} {e}"
        eid = e["id"]
        s, sc = http("POST", f"/admin/elections/{eid}/scope", {"lga_ids": lga_map[p["key"]]}, token=tok)
        assert s == 200 and sc.get("pus", 0) > 0, f"scope failed {p['key']}: {s} {sc}"
        s, st = http("PUT", f"/admin/elections/{eid}/status", {"status": "live"}, token=tok)
        assert s == 200, f"status failed {p['key']}: {s} {st}"

        # One agent provisioned by the client admin (inheritance path)
        async with AsyncSessionLocal() as db:
            pu = (await db.execute(text(
                "SELECT pu.id FROM polling_units pu JOIN wards w ON w.id = pu.ward_id "
                "WHERE w.lga_id = :l AND pu.expected_latitude IS NOT NULL LIMIT 1"),
                {"l": lga_map[p["key"]][0]})).first()
            await db.commit()
        s, pr = http("POST", "/admin/provision-agents", {
            "emails": [p["agent"]], "polling_unit_id": pu[0], "election_id": eid}, token=tok)
        assert s in (200, 201), f"provision failed {p['key']}: {s} {pr}"
        agent_creds = (pr.get("provisioned") or {}).get(p["agent"], {})

        out["missions"].append({
            "client": p["client"], "client_id": client_ids[p["key"]],
            "election": p["election"]["name"], "code": p["election"]["code"],
            "pus_in_scope": sc.get("pus"),
            "admin": {"email": p["admin"], "password": ADM_PASS},
            "agent": {"email": p["agent"], **agent_creds},
        })
        print(f"[OK] {p['key']}: {p['election']['code']}  pus={sc.get('pus')}", flush=True)

    # Isolation proof across the four client admins
    s, lp = http("GET", "/admin/elections", token=plat)
    plat_codes = sorted(e["code"] for e in lp.get("elections", []))
    print(f"[PLATFORM] sees: {plat_codes}", flush=True)
    for p in PLAN:
        s, d = http("POST", "/auth/login", {"email": p["admin"], "password": ADM_PASS})
        tok = d.get("access_token")
        s, lst = http("GET", "/admin/elections", token=tok)
        codes = sorted(e["code"] for e in lst.get("elections", []))
        own = p["election"]["code"]
        ok = codes == [own]
        print(f"[ISOLATION] {p['key']}: sees {codes} -> {'PASS' if ok else 'FAIL'}", flush=True)
        s, ag = http("GET", "/admin/agents", token=tok)
        import json as _j
        blob = _j.dumps(ag)
        others = [q["agent"] for q in PLAN if q["key"] != p["key"]]
        leak = any(o in blob for o in others)
        print(f"[ISOLATION] {p['key']}: agent list leak={leak} -> {'PASS' if not leak else 'FAIL'}", flush=True)

    print("\n=== DRILL CREDENTIALS ===")
    print(json.dumps(out, indent=2))

asyncio.run(main())
