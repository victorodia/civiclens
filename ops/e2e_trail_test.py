#!/usr/bin/env python3
"""End-to-end field test for the GPS presence trail.

Flow: provision agent on a real PU with coordinates -> negative geofence
check (5km away must be rejected) -> verify entry on-site -> 3 location
pings -> signed result submission -> admin trail shows the full story.
Second agent submits with a stale check-in and no pings -> trail flagged.
Everything is cleaned up afterwards.
"""
import base64
import hashlib
import hmac
import json
import secrets
import subprocess
import urllib.request
import urllib.error
import uuid

BASE = "https://193.122.220.182.nip.io"
_run = secrets.token_hex(4)
ADMIN_EMAIL = f"cl-e2e-admin-{_run}@civiclens.io"
AGENT1 = f"cl-e2e-agent1-{_run}@civiclens.io"
AGENT2 = f"cl-e2e-agent2-{_run}@civiclens.io"
_symbols = "#!@$%*-_=+"
ADMIN_PW = secrets.token_urlsafe(18) + secrets.choice(_symbols)
AGENT_PW = secrets.token_urlsafe(18) + secrets.choice(_symbols)
FP = "MOCKED_PHONE_ID"
ADMIN_ID = str(uuid.uuid4())

passed, failed = [], []


def check(name, cond, detail):
    (passed if cond else failed).append(name)
    print(f"{'PASS' if cond else 'FAIL'}  {name}  [{detail}]", flush=True)


def call(method, path, body=None, headers=None, raw=None, timeout=60):
    req = urllib.request.Request(BASE + path, method=method)
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    if body is not None and raw is None:
        req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, data=data, timeout=timeout) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except Exception:
            return e.code, {}
    except Exception as e:
        return -1, {"detail": str(e)}


def sql(stmt):
    return subprocess.run(
        ["sudo", "docker", "exec", "civiclens-db", "psql", "-U", "civiclens_user",
         "-d", "civiclens", "-t", "-c", stmt], check=True, capture_output=True, text=True).stdout


def sqlrows(stmt):
    return [ln.strip() for ln in sql(stmt).splitlines() if ln.strip()]


def sign(pu_code, a, b, c, key):
    msg = f"{pu_code}|{a}|{b}|{c}".encode()
    return base64.b64encode(hmac.new(key.encode(), msg, hashlib.sha256).digest()).decode()


# ---------- pick two real PUs that have coordinates ----------
rows = sqlrows(
    "SELECT id || '|' || pu_code || '|' || expected_latitude || '|' || expected_longitude "
    "FROM polling_units WHERE expected_latitude IS NOT NULL "
    "AND id NOT IN (SELECT pu_id FROM results) LIMIT 2")
pu1 = dict(zip(("id", "code", "lat", "lng"), rows[0].split("|")))
pu2 = dict(zip(("id", "code", "lat", "lng"), rows[1].split("|")))
lat1, lng1 = float(pu1["lat"]), float(pu1["lng"])
print(f"Using PU1 {pu1['code']} ({lat1},{lng1}) and PU2 {pu2['code']}", flush=True)

# ---------- temp admin ----------
h = subprocess.run(
    ["sudo", "docker", "exec", "civiclens-backend", "python3", "-c",
     "from passlib.context import CryptContext; "
     "print(CryptContext(schemes=['argon2'],deprecated='auto').hash('" + ADMIN_PW + "'))"],
    capture_output=True, text=True, check=True).stdout.strip()
sql(f"INSERT INTO users (id,email,hashed_password,full_name,role,is_active,requires_password_reset) "
    f"VALUES ('{ADMIN_ID}','{ADMIN_EMAIL}','{h}','E2E Admin','admin',true,false) "
    f"ON CONFLICT (email) DO NOTHING;")
st, r = call("POST", "/auth/login", {"email": ADMIN_EMAIL, "password": ADMIN_PW})
admin_tok = r.get("access_token")
check("setup: admin login", bool(admin_tok), f"status={st}")
AH = {"Authorization": f"Bearer {admin_tok}"}


def provision(email, pu_id):
    st, r = call("POST", "/admin/provision-agents",
                 {"emails": [email], "polling_unit_id": pu_id}, headers=AH)
    key = (r.get("provisioned") or {}).get(email, {}).get("signing_key")
    return st, key


def agent_login(email):
    call("POST", "/auth/secure-initialization",
         {"email": email, "new_password": AGENT_PW, "duress_password": "Duress#000x"})
    st, r = call("POST", "/auth/login",
                 {"email": email, "password": AGENT_PW, "device_fingerprint": FP})
    return r.get("access_token")


def submit_result(code, key, email, gh):
    payload = {"pu_code": code, "agent_email": email,
               "party_a_votes": 120, "party_b_votes": 98, "party_c_votes": 44,
               "total_valid": 262, "signature": sign(code, 120, 98, 44, key),
               "captured_at": "2026-10-11T09:00:00Z",
               "latitude": lat1, "longitude": lng1}
    return call("POST", "/results/submit", payload, headers=gh)


# ---------- agent 1: full happy path ----------
st, key1 = provision(AGENT1, pu1["id"])
check("provision agent1 on coord-PU", st == 200 and bool(key1), f"status={st} key={'yes' if key1 else 'NO'}")
tok1 = agent_login(AGENT1)
check("agent1 login", bool(tok1), f"tok={'yes' if tok1 else 'NO'}")
G1 = {"Authorization": f"Bearer {tok1}", "X-Device-Fingerprint": FP}

# negative geofence: ~5 km north must be rejected now that anchors exist
st, r = call("POST", "/auth/agent/check-in",
             {"email": AGENT1, "latitude": lat1 + 0.045, "longitude": lng1}, headers=G1)
check("geofence rejects check-in 5km away", st == 403, f"got {st} {r.get('detail','')[:60]}")

# verify entry on-site
st, r = call("POST", "/auth/agent/check-in",
             {"email": AGENT1, "latitude": lat1, "longitude": lng1}, headers=G1)
check("verify entry at anchor", st == 200, f"got {st}")

# 3 pings with realistic jitter
ok_pings = 0
for i, (dlat, dlng) in enumerate([(0.0, 0.0), (0.0004, -0.0003), (-0.0002, 0.0005)]):
    st, r = call("POST", "/auth/agent/location-ping",
                 {"email": AGENT1, "latitude": lat1 + dlat, "longitude": lng1 + dlng}, headers=G1)
    if st == 200:
        ok_pings += 1
        interval = r.get("next_ping_in_minutes")
check("3 location pings accepted", ok_pings == 3, f"ok={ok_pings} interval={interval}min")

# submit signed result
st, r = submit_result(pu1["code"], key1, AGENT1, G1)
rid1 = r.get("result_id")
check("signed result submission", st in (200, 201) and bool(rid1), f"status={st}")

# admin trail view
st, trail = call("GET", f"/admin/results/{rid1}/trail", headers=AH)
check("admin trail endpoint 200", st == 200, f"got {st}")
check("trail has anchor + check-in + submission",
      bool(trail.get("anchor")) and bool(trail.get("check_in")) and bool(trail.get("submission")),
      f"anchor={'yes' if trail.get('anchor') else 'NO'}")
check("trail shows all 3 pings, none flagged",
      len(trail.get("pings", [])) == 3 and not any(p["outside_geofence"] for p in trail.get("pings", []))
      and trail.get("gps_trail_flag") is False,
      f"pings={len(trail.get('pings', []))} flag={trail.get('gps_trail_flag')}")

# ---------- agent 2: thin trail must flag ----------
st, key2 = provision(AGENT2, pu2["id"])
tok2 = agent_login(AGENT2)
G2 = {"Authorization": f"Bearer {tok2}", "X-Device-Fingerprint": FP}
lat2, lng2 = float(pu2["lat"]), float(pu2["lng"])
call("POST", "/auth/agent/check-in", {"email": AGENT2, "latitude": lat2, "longitude": lng2}, headers=G2)
# simulate a 2-hour on-site window with zero pings
sql(f"UPDATE users SET last_check_in = now() - interval '2 hours' WHERE email = '{AGENT2}'")
st, r = call("POST", "/results/submit",
             {"pu_code": pu2["code"], "agent_email": AGENT2,
              "party_a_votes": 55, "party_b_votes": 60, "party_c_votes": 12,
              "total_valid": 127, "signature": sign(pu2["code"], 55, 60, 12, key2),
              "captured_at": "2026-10-11T11:00:00Z", "latitude": lat2, "longitude": lng2},
             headers=G2)
rid2 = r.get("result_id")
check("agent2 submission accepted (flag must not block)", st in (200, 201), f"status={st}")
st, trail2 = call("GET", f"/admin/results/{rid2}/trail", headers=AH)
check("thin trail flagged for review", trail2.get("gps_trail_flag") is True,
      f"flag={trail2.get('gps_trail_flag')} pings={len(trail2.get('pings', []))}")

# ---------- cleanup ----------
for t, e, p in ((rid1, AGENT1, pu1), (rid2, AGENT2, pu2)):
    if t:
        sql(f"DELETE FROM results WHERE id = '{t}'")
    sql(f"DELETE FROM agent_location_pings WHERE agent_id IN (SELECT id FROM users WHERE email = '{e}')")
    sql(f"DELETE FROM users WHERE email = '{e}'")
sql(f"DELETE FROM users WHERE email = '{ADMIN_EMAIL}'")
print("cleanup: test accounts, results, pings removed", flush=True)

print(f"\nRESULT: {len(passed)} passed, {len(failed)} failed")
for f in failed:
    print("FAILED:", f)
