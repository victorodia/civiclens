"""
Functional test for client (institution) tenancy isolation.
Runs INSIDE the backend container:
  docker exec civiclens-backend python -u /tmp/test_client_isolation.py

Scenario: two independent institutions (Client A, Client B), each with its
own admin, election, and provisioned agent. Verifies that neither institution
can see or touch the other's data, while a platform super-admin (client_id
NULL) sees everything.

  I1  platform admin can create clients A and B
  I2  client admin GET /admin/clients sees only own client
  I3  client admin creating an election lands in own client
  I4  client admin election list excludes the other institution's election
  I5  client A gets 404 (not 403) on B's election status/scope/assignments
  I6  symmetric: client B gets 404 on A's election
  I7  client A cannot assign B's agent (404)
  I8  client A provisioning against B's election -> 404
  I9  platform admin provisioning with mismatched client/election -> 404
  I10 provisioned agent inherits creator's client; agent login shows only
      own institution's election
  I11 client admin monitor map without election_id -> 403
  I12 client admin monitor map with other institution's election -> 404
  I13 client admin scoped monitor map on own election -> 200
  I14 platform admin unscoped monitor map -> 200
  I15 client admin workforce/agent list excludes other institution's agents
  I16 client admin stats/collation -> 200 (scoped aggregates)
Cleans up all test rows at the end.
"""
import asyncio
import json
import urllib.request
import urllib.error

BASE = "http://localhost:8001"
PASS = "TestPass#2026x"


def http(method, path, body=None, token=None, timeout=30):
    req = urllib.request.Request(BASE + path, method=method)
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, data=data, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or "{}")
        except Exception:
            return e.code, {}


async def main():
    from app.db import AsyncSessionLocal
    from app.security import get_password_hash
    from sqlalchemy import text

    print("[T] setup start", flush=True)
    async with AsyncSessionLocal() as db:
        # Platform admin (client_id NULL)
        row = (await db.execute(text(
            "SELECT id FROM users WHERE email = 'cltest.platform@example.com'"))).first()
        if not row:
            await db.execute(text(
                "INSERT INTO users (id, email, hashed_password, full_name, role, is_active, "
                "requires_password_reset) VALUES ('cltest-platform-1', 'cltest.platform@example.com', "
                ":h, 'CL Platform Admin', 'admin', true, false)"), {"h": get_password_hash(PASS)})
        # One small LGA to scope both elections to
        lga_row = (await db.execute(text(
            "SELECT w.lga_id, count(*) AS n FROM polling_units pu "
            "JOIN wards w ON w.id = pu.ward_id "
            "WHERE pu.expected_latitude IS NOT NULL "
            "GROUP BY w.lga_id ORDER BY n ASC LIMIT 1"))).first()
        lga_id = lga_row[0]
        pu_rows = (await db.execute(text(
            "SELECT pu.id FROM polling_units pu JOIN wards w ON w.id = pu.ward_id "
            "WHERE w.lga_id = :l AND pu.expected_latitude IS NOT NULL LIMIT 2"),
            {"l": lga_id})).all()
        pu_a, pu_b = pu_rows[0][0], pu_rows[1][0]
        await db.commit()
    print(f"[T] setup done lga={lga_id}", flush=True)

    passed, failed = [], []
    def check(t, cond, extra=""):
        (passed if cond else failed).append(t)
        print(("PASS " if cond else "FAIL ") + t + (f"  [{extra}]" if extra else ""))

    # Platform login
    s, login = http("POST", "/auth/login", {"email": "cltest.platform@example.com", "password": PASS})
    plat_tok = login.get("access_token")
    check("I0 platform admin login", s == 200 and plat_tok, f"status={s}")

    # I1 create clients
    s, ca = http("POST", "/admin/clients", {"name": "ZZ Institution A"}, token=plat_tok)
    s2, cb = http("POST", "/admin/clients", {"name": "ZZ Institution B"}, token=plat_tok)
    client_a, client_b = ca.get("id"), cb.get("id")
    check("I1 platform creates clients", s == 201 and s2 == 201 and client_a and client_b,
          f"{client_a} / {client_b}")

    # Client admins (created directly in DB with client_id set)
    async with AsyncSessionLocal() as db:
        await db.execute(text(
            "INSERT INTO users (id, email, hashed_password, full_name, role, is_active, "
            "requires_password_reset, client_id) VALUES ('cltest-adm-a', 'cltest.adm.a@example.com', "
            ":h, 'Admin A', 'admin', true, false, :c)"), {"h": get_password_hash(PASS), "c": client_a})
        await db.execute(text(
            "INSERT INTO users (id, email, hashed_password, full_name, role, is_active, "
            "requires_password_reset, client_id) VALUES ('cltest-adm-b', 'cltest.adm.b@example.com', "
            ":h, 'Admin B', 'admin', true, false, :c)"), {"h": get_password_hash(PASS), "c": client_b})
        await db.commit()

    s, la = http("POST", "/auth/login", {"email": "cltest.adm.a@example.com", "password": PASS})
    tok_a = la.get("access_token")
    s, lb = http("POST", "/auth/login", {"email": "cltest.adm.b@example.com", "password": PASS})
    tok_b = lb.get("access_token")
    check("I0b client admins login", bool(tok_a and tok_b))

    # I2 clients list scoping
    s, la_list = http("GET", "/admin/clients", token=tok_a)
    names_a = [c.get("name") for c in la_list.get("clients", [])]
    check("I2 client admin sees only own client", s == 200 and names_a == ["ZZ Institution A"],
          f"names={names_a}")

    # I3 each client admin creates an election (no client_id payload)
    s, ea = http("POST", "/admin/elections", {
        "name": "ZZ A Senatorial", "code": "ZZISCA", "type": "senatorial",
        "party_a_name": "PA", "party_b_name": "PB", "party_c_name": "PC"}, token=tok_a)
    s2, eb = http("POST", "/admin/elections", {
        "name": "ZZ B Gubernatorial", "code": "ZZISCB", "type": "gubernatorial",
        "party_a_name": "PA", "party_b_name": "PB", "party_c_name": "PC"}, token=tok_b)
    elec_a, elec_b = ea.get("id"), eb.get("id")
    check("I3 client admins create elections", s == 201 and s2 == 201 and elec_a and elec_b,
          f"status={s}/{s2}")

    # Scope + live both
    for tok, eid in ((tok_a, elec_a), (tok_b, elec_b)):
        s, sc = http("POST", f"/admin/elections/{eid}/scope", {"lga_ids": [lga_id]}, token=tok)
        assert s == 200 and sc.get("pus", 0) > 0, f"scope failed {s} {sc}"
        s, st = http("PUT", f"/admin/elections/{eid}/status", {"status": "live"}, token=tok)
        assert s == 200, f"status failed {s} {st}"
    print("[T] both elections scoped + live", flush=True)

    # I4 election list isolation
    s, lst_a = http("GET", "/admin/elections", token=tok_a)
    codes_a = {e["code"] for e in lst_a.get("elections", [])}
    check("I4 A list excludes B election", s == 200 and "ZZISCA" in codes_a and "ZZISCB" not in codes_a,
          f"codes={sorted(codes_a)}")
    s, lst_p = http("GET", "/admin/elections", token=plat_tok)
    codes_p = {e["code"] for e in lst_p.get("elections", [])}
    check("I4b platform sees both", "ZZISCA" in codes_p and "ZZISCB" in codes_p, f"n={len(codes_p)}")

    # I5/I6 cross-institution 404s
    s, r = http("PUT", f"/admin/elections/{elec_b}/status", {"status": "closed"}, token=tok_a)
    check("I5 A touching B election status -> 404", s == 404, f"status={s}")
    s, r = http("POST", f"/admin/elections/{elec_b}/scope", {"lga_ids": [lga_id]}, token=tok_a)
    check("I5b A reading B scope -> 404", s == 404, f"status={s}")
    s, r = http("GET", f"/admin/elections/{elec_a}/assignments", token=tok_b)
    check("I6 B reading A assignments -> 404", s == 404, f"status={s}")

    # Provision one agent per institution
    s, pa = http("POST", "/admin/provision-agents", {
        "emails": ["zz.agent.a@example.com"], "polling_unit_id": pu_a,
        "election_id": elec_a}, token=tok_a)
    s2, pb = http("POST", "/admin/provision-agents", {
        "emails": ["zz.agent.b@example.com"], "polling_unit_id": pu_b,
        "election_id": elec_b}, token=tok_b)
    agent_a = (pa.get("provisioned") or {}).get("zz.agent.a@example.com", {})
    agent_b = (pb.get("provisioned") or {}).get("zz.agent.b@example.com", {})
    check("I7 provision agents in own institutions", s in (200, 201) and s2 in (200, 201)
          and agent_a.get("signing_key") and agent_b.get("signing_key"),
          f"{s}/{s2} {pa} {pb}")
    # Find their user ids
    async with AsyncSessionLocal() as db:
        ra = (await db.execute(text("SELECT id FROM users WHERE email='zz.agent.a@example.com'"))).first()
        rb = (await db.execute(text("SELECT id FROM users WHERE email='zz.agent.b@example.com'"))).first()
        uid_a, uid_b = ra[0], rb[0]
        await db.execute(text(
            "UPDATE users SET requires_password_reset=false, device_fingerprint='MOCKED_PHONE_ID', "
            "hashed_password=:h WHERE email IN ('zz.agent.a@example.com','zz.agent.b@example.com')"),
            {"h": get_password_hash(PASS)})
        await db.commit()

    # I8 A cannot assign B's agent
    s, r = http("POST", f"/admin/agents/{uid_b}/assignments",
                {"election_id": elec_a, "pu_id": pu_a}, token=tok_a)
    check("I8 A assigning B agent -> 404", s == 404, f"status={s}")

    # I9 cross-client provisioning rejected
    s, r = http("POST", "/admin/provision-agents", {
        "emails": ["zz.intruder@example.com"], "polling_unit_id": pu_a,
        "election_id": elec_b}, token=tok_a)
    check("I9 A provisioning into B election -> 404", s == 404, f"status={s}")
    s, r = http("POST", "/admin/provision-agents", {
        "emails": ["zz.intruder2@example.com"], "polling_unit_id": pu_a,
        "election_id": elec_a, "client_id": client_b}, token=plat_tok)
    check("I9b platform client/election mismatch -> 404", s == 404, f"status={s}")

    # I10 agent inherits client; sees only own election
    s, al = http("POST", "/auth/login", {"email": "zz.agent.a@example.com", "password": PASS,
                                         "device_fingerprint": "MOCKED_PHONE_ID"})
    assigns = {a["election_code"] for a in al.get("assignments", [])}
    check("I10 agent A sees only A election", s == 200 and assigns == {"ZZISCA"}, f"codes={assigns}")
    s, bl = http("POST", "/auth/login", {"email": "zz.agent.b@example.com", "password": PASS,
                                         "device_fingerprint": "MOCKED_PHONE_ID"})
    assigns_b = {a["election_code"] for a in bl.get("assignments", [])}
    check("I10b agent B sees only B election", s == 200 and assigns_b == {"ZZISCB"}, f"codes={assigns_b}")

    # I11/I12/I13/I14 monitor map scoping
    s, r = http("GET", "/admin/monitor/map", token=tok_a)
    check("I11 A unscoped map -> 403", s == 403, f"status={s}")
    s, r = http("GET", f"/admin/monitor/map?election_id={elec_b}", token=tok_a)
    check("I12 A viewing B map -> 404", s == 404, f"status={s}")
    s, r = http("GET", f"/admin/monitor/map?election_id={elec_a}", token=tok_a)
    check("I13 A viewing own map -> 200", s == 200, f"status={s}")
    s, r = http("GET", "/admin/monitor/map", token=plat_tok, timeout=90)
    check("I14 platform unscoped map -> 200", s == 200, f"status={s}")

    # I15 workforce list scoping
    s, r = http("GET", "/admin/agents", token=tok_a)
    blob = json.dumps(r)
    check("I15 A agent list excludes B agent", s == 200
          and "zz.agent.b@example.com" not in blob
          and "zz.agent.a@example.com" in blob, f"status={s}")
    s, r = http("GET", "/admin/workforce-status", token=tok_a)
    check("I15b A workforce-status -> 200", s == 200, f"status={s}")

    # I16 collation scoped
    s, r = http("GET", "/admin/stats/collation", token=tok_a)
    check("I16 A collation -> 200", s == 200, f"status={s}")

    # Cleanup in FK order
    async with AsyncSessionLocal() as db:
        for eid in (elec_a, elec_b):
            await db.execute(text("DELETE FROM results WHERE election_id = :e"), {"e": eid})
            await db.execute(text("DELETE FROM agent_location_pings WHERE election_id = :e"), {"e": eid})
            await db.execute(text("DELETE FROM agent_checkins WHERE election_id = :e"), {"e": eid})
            await db.execute(text("DELETE FROM agent_assignments WHERE election_id = :e"), {"e": eid})
            await db.execute(text("DELETE FROM election_polling_units WHERE election_id = :e"), {"e": eid})
            await db.execute(text("DELETE FROM elections WHERE id = :e"), {"e": eid})
        await db.execute(text(
            "DELETE FROM users WHERE email IN ('zz.agent.a@example.com','zz.agent.b@example.com',"
            "'zz.intruder@example.com','zz.intruder2@example.com','cltest.adm.a@example.com',"
            "'cltest.adm.b@example.com','cltest.platform@example.com')"))
        await db.execute(text("DELETE FROM clients WHERE id IN (:a, :b)"), {"a": client_a, "b": client_b})
        await db.commit()
    print("[CLEANUP] isolation test rows removed")

    print(f"\nRESULT: {len(passed)} passed, {len(failed)} failed" + (f" -> {failed}" if failed else ""))


asyncio.run(main())
