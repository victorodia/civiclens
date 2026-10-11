"""
Functional test for multi-election scoping. Runs INSIDE the backend container:
  docker exec civiclens-backend python -u /tmp/test_multi_election.py

Creates a throwaway election (code ZZTEST), scopes it to one small LGA,
accredits an existing agent for a PU in it, then verifies:
  T1  admin can list elections (>=1)
  T2  election create -> 201
  T3  scope materializes PUs
  T4  agent login returns BOTH election assignments with party labels
  T5  cross-election replay: GENERAL-signed payload submitted to ZZTEST -> 403
  T6  ZZTEST-signed payload BEFORE check-in -> 403 muster roll
  T7  check-in for ZZTEST -> success (session created)
  T8  submit ZZTEST-signed payload -> success
  T9  duplicate submit for same election -> 409
  T10 monitor map scoped to ZZTEST returns only that election's data
Cleans up all ZZTEST rows at the end.
"""
import asyncio
import hashlib
import hmac
import json
import urllib.request
import urllib.error
from datetime import datetime

BASE = "http://localhost:8001"
PASS = "TestPass#2026x"


def http(method, path, body=None, token=None, headers=None):
    req = urllib.request.Request(BASE + path, method=method)
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, data=data, timeout=30) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or "{}")
        except Exception:
            return e.code, {}


def sign(pu_code, election_code, a, b, c, key):
    import base64
    s = f"{pu_code}|{election_code}|{a}|{b}|{c}"
    return base64.b64encode(hmac.new(key.encode(), s.encode(), hashlib.sha256).digest()).decode()


async def main():
    from app.db import AsyncSessionLocal
    from app.models import User
    from app.security import get_password_hash
    from sqlalchemy import text

    print("[T] setup start", flush=True)
    async with AsyncSessionLocal() as db:
        # Ensure a test admin
        admin = (await db.execute(text("SELECT id FROM users WHERE email = 'cltest.admin@example.com'"))).first()
        if not admin:
            await db.execute(text(
                "INSERT INTO users (id, email, hashed_password, full_name, role, is_active, requires_password_reset) "
                "VALUES ('cltest-admin-0001', 'cltest.admin@example.com', :h, 'CL Test Admin', 'admin', true, false)"
            ), {"h": get_password_hash(PASS)})
            await db.commit()
        print("[T] admin ensured", flush=True)
        # Pick an agent
        row = (await db.execute(text(
            "SELECT u.email, u.device_signing_key, u.id, a.pu_id, pu.pu_code "
            "FROM agent_assignments a JOIN users u ON u.id = a.agent_id "
            "JOIN polling_units pu ON pu.id = a.pu_id "
            "WHERE a.election_id = 'general-election' LIMIT 1"
        ))).first()
        print("[T] agent row fetched", flush=True)
        agent_email, agent_key, agent_id, gen_pu_id, gen_pu_code = row
        await db.execute(text(
            "UPDATE users SET hashed_password = :h, device_fingerprint = 'MOCKED_PHONE_ID', "
            "requires_password_reset = false WHERE id = :id"
        ), {"h": get_password_hash(PASS), "id": agent_id})
        print("[T] update done", flush=True)
        print(f"[T] agent picked: {agent_email}", flush=True)
        # LGA, then any PU in it
        print("[T] before update", flush=True)
        lga_row = (await db.execute(text(
            "SELECT w.lga_id, count(*) AS n "
            "FROM polling_units pu JOIN wards w ON w.id = pu.ward_id "
            "WHERE pu.expected_latitude IS NOT NULL "
            "GROUP BY w.lga_id ORDER BY n ASC LIMIT 1"
        ))).first()
        lga_id, _n = lga_row
        print("[T] lga done", flush=True)
        pu_row = (await db.execute(text(
            "SELECT pu.id, pu.pu_code, pu.expected_latitude, pu.expected_longitude "
            "FROM polling_units pu JOIN wards w ON w.id = pu.ward_id "
            "WHERE w.lga_id = :l AND pu.expected_latitude IS NOT NULL AND pu.id <> :p "
            "LIMIT 1"
        ), {"l": lga_id, "p": gen_pu_id})).first()
        test_pu_id, test_pu_code, tlat, tlng = pu_row
        await db.commit()
    print(f"[T] setup done", flush=True)
    print(f"[SETUP] agent={agent_email} general_pu={gen_pu_code} test_pu={test_pu_code} lga={lga_id}")

    passed, failed = [], []
    def check(t, cond, extra=""):
        (passed if cond else failed).append(t)
        print(("PASS " if cond else "FAIL ") + t + (f"  [{extra}]" if extra else ""))

    # Admin login
    s, login = http("POST", "/auth/login", {"email": "cltest.admin@example.com", "password": PASS})
    admin_tok = login.get("access_token")
    check("T0 admin login", s == 200 and admin_tok, f"status={s}")

    # T1 list elections
    s, lst = http("GET", "/admin/elections", token=admin_tok)
    eids = {e["code"]: e["id"] for e in lst.get("elections", [])}
    check("T1 list elections", s == 200 and "GENERAL" in eids, f"n={len(eids)}")

    # T2 create test election
    s, created = http("POST", "/admin/elections", {
        "name": "ZZ Test Senatorial", "code": "ZZTEST", "type": "senatorial",
        "party_a_name": "Red Party", "party_b_name": "Blue Party", "party_c_name": "Green Party"},
        token=admin_tok)
    zz_id = created.get("id")
    check("T2 create election", s == 201 and zz_id, f"status={s}")

    # T3 scope to one LGA + set live
    s, sc = http("POST", f"/admin/elections/{zz_id}/scope", {"lga_ids": [lga_id]}, token=admin_tok)
    check("T3 scope", s == 200 and sc.get("pus", 0) > 0, f"pus={sc.get('pus')}")
    s, st = http("PUT", f"/admin/elections/{zz_id}/status", {"status": "live"}, token=admin_tok)
    check("T3b set live", s == 200, f"status={s}")

    # T3c assignment for the agent
    s, asn = http("POST", f"/admin/agents/{agent_id}/assignments",
                  {"election_id": zz_id, "pu_id": test_pu_id}, token=admin_tok)
    check("T3c assign agent to ZZTEST", s == 201, f"status={s} {asn}")

    # T4 agent login shows both elections
    s, alogin = http("POST", "/auth/login",
                     {"email": agent_email, "password": PASS, "device_fingerprint": "MOCKED_PHONE_ID"})
    agent_tok = alogin.get("access_token")
    assigns = {a["election_code"]: a for a in alogin.get("assignments", [])}
    check("T4 agent login assignments", s == 200 and "GENERAL" in assigns and "ZZTEST" in assigns,
          f"codes={list(assigns)}")
    check("T4b party labels per election",
          assigns.get("ZZTEST", {}).get("party_a_name") == "Red Party",
          f"a={assigns.get('ZZTEST', {}).get('party_a_name')}")

    dev = {"X-Device-Fingerprint": "MOCKED_PHONE_ID"}
    payload = {"pu_code": test_pu_code, "agent_email": agent_email,
               "party_a_votes": 10, "party_b_votes": 20, "party_c_votes": 3,
               "total_valid": 33, "captured_at": datetime.utcnow().isoformat() + "Z"}

    # T5 cross-election replay: signed for GENERAL, submitted to ZZTEST
    p = dict(payload, election_id=zz_id,
             signature=sign(test_pu_code, "GENERAL", 10, 20, 3, agent_key))
    s, r = http("POST", "/results/submit", p, token=agent_tok, headers=dev)
    check("T5 cross-election replay rejected", s == 403, f"status={s} {r.get('detail', '')[:60]}")

    # T6 correct election signature but no check-in for ZZTEST
    p = dict(payload, election_id=zz_id,
             signature=sign(test_pu_code, "ZZTEST", 10, 20, 3, agent_key))
    s, r = http("POST", "/results/submit", p, token=agent_tok, headers=dev)
    check("T6 submit before verify-entry rejected", s == 403 and "Verify Entry" in r.get("detail", ""),
          f"status={s} {r.get('detail', '')[:60]}")

    # T7 check-in for ZZTEST
    s, r = http("POST", "/auth/agent/check-in",
                {"email": agent_email, "election_id": zz_id,
                 "latitude": float(tlat), "longitude": float(tlng)},
                token=agent_tok)
    check("T7 verify-entry for ZZTEST", s == 200, f"status={s} {r}")

    # T8 proper submit for ZZTEST
    s, r = http("POST", "/results/submit", p, token=agent_tok, headers=dev)
    check("T8 submit for ZZTEST", s == 200 and r.get("status") == "success", f"status={s} {r.get('detail', '')[:60]}")

    # T9 duplicate for same election -> 409 (GENERAL at same PU still open)
    s, r = http("POST", "/results/submit", p, token=agent_tok, headers=dev)
    check("T9 duplicate in same election rejected", s == 409, f"status={s}")

    # T10 scoped monitor map
    s, m = http("GET", f"/admin/monitor/map?election_id={zz_id}", token=admin_tok)
    subs = m.get("counters", {}).get("submitted", -1)
    check("T10 monitor map scoped", s == 200 and subs == 1, f"submitted={subs}")

    # Cleanup: remove ZZTEST artifacts
    async with AsyncSessionLocal() as db:
        await db.execute(text("DELETE FROM results WHERE election_id = :e"), {"e": zz_id})
        await db.execute(text("DELETE FROM agent_checkins WHERE election_id = :e"), {"e": zz_id})
        await db.execute(text("DELETE FROM agent_assignments WHERE election_id = :e"), {"e": zz_id})
        await db.execute(text("DELETE FROM election_polling_units WHERE election_id = :e"), {"e": zz_id})
        await db.execute(text("DELETE FROM elections WHERE id = :e"), {"e": zz_id})
        await db.execute(text("DELETE FROM users WHERE id = 'cltest-admin-0001'"))
        await db.commit()
    print("[CLEANUP] ZZTEST artifacts removed")

    print(f"\nRESULT: {len(passed)} passed, {len(failed)} failed" + (f" -> {failed}" if failed else ""))


asyncio.run(main())
