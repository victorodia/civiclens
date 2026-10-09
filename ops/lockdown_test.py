#!/usr/bin/env python3
"""CivicLens endpoint lockdown integration test (run on server, via gateway).

Temp accounts use RANDOM credentials generated per run, so even while the
suite is executing, there is no known-password admin window to exploit.
"""
import base64
import hashlib
import hmac
import json
import secrets
import string
import subprocess
import urllib.request
import urllib.error

BASE = "https://193.122.220.182.nip.io"
_run = secrets.token_hex(4)
ADMIN_EMAIL = f"cl-temp-{_run}@civiclens.io"
AGENT_EMAIL = f"cl-agent-{_run}@civiclens.io"
_symbols = "#!@$%*-_=+"
ADMIN_PW = secrets.token_urlsafe(18) + secrets.choice(_symbols)
AGENT_PW = secrets.token_urlsafe(18) + secrets.choice(_symbols)
FP = "MOCKED_PHONE_ID"
OCCUPIED_PU = "DEL-03-03-010"


def sign_payload(pu_code, a, b, c, key):
    """Same construction as the agent portal: puCode|A|B|C, HMAC-SHA256, base64."""
    msg = f"{pu_code}|{a}|{b}|{c}".encode()
    return base64.b64encode(hmac.new(key.encode(), msg, hashlib.sha256).digest()).decode()

# 1x1 transparent PNG
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)

passed, failed = [], []


def call(method, path, body=None, headers=None, raw=None):
    req = urllib.request.Request(BASE + path, method=method)
    data = None
    if raw is not None:
        data = raw
    elif body is not None:
        data = json.dumps(body).encode()
        req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, data=data, timeout=30) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except Exception:
            return e.code, {}
    except Exception as e:
        return -1, {"detail": str(e)}


def check(name, cond, detail):
    (passed if cond else failed).append(name)
    print(f"{'PASS' if cond else 'FAIL'}  {name}  [{detail}]")


def sql(stmt):
    subprocess.run(
        ["sudo", "docker", "exec", "civiclens-db", "psql", "-U", "civiclens_user",
         "-d", "civiclens", "-c", stmt], check=True, capture_output=True)


# ---------- setup: temporary admin account with a proper Argon2 hash ----------
h = subprocess.run(
    ["sudo", "docker", "exec", "civiclens-backend", "python3", "-c",
     "from passlib.context import CryptContext; "
     "print(CryptContext(schemes=['argon2'],deprecated='auto').hash('" + ADMIN_PW + "'))"],
    capture_output=True, text=True, check=True).stdout.strip()
sql(f"INSERT INTO users (id,email,hashed_password,full_name,role,is_active,requires_password_reset) "
    f"VALUES ('cl-temp-admin-0000-0000-000000000001','{ADMIN_EMAIL}','{h}','Temp Admin','admin',true,false) "
    f"ON CONFLICT (email) DO NOTHING;")

try:
    st, r = call("POST", "/auth/login", {"email": ADMIN_EMAIL, "password": ADMIN_PW})
    admin_tok = r.get("access_token")
    check("setup: temp admin login", bool(admin_tok), f"status={st}")
    AH = {"Authorization": f"Bearer {admin_tok}"}

    # Warmup: the first wallet-balance hit after a backend boot pays the lazy
    # web3 import inside a worker thread (can exceed a minute on this VM). Do
    # it here with a long timeout so the real assertion below hits the cache.
    try:
        warm = urllib.request.Request(BASE + "/admin/wallet-balance")
        warm.add_header("Authorization", f"Bearer {admin_tok}")
        with urllib.request.urlopen(warm, timeout=180) as wr:
            wr.read()
    except Exception as e:
        print(f"WARN  wallet-balance warmup failed: {e}")

    # ---------- negative: no token anywhere ----------
    st, r = call("POST", "/upload/form-ec8a", raw=PNG, headers={"Content-Type": "image/png"})
    check("upload no token -> 401", st == 401, f"got {st}")
    st, r = call("POST", "/auth/agent/check-in", {"email": AGENT_EMAIL, "latitude": 0, "longitude": 0})
    check("check-in no token -> 401", st == 401, f"got {st}")
    st, r = call("GET", f"/admin/mfa/setup?email={ADMIN_EMAIL}")
    check("mfa/setup no token -> 401", st == 401, f"got {st}")
    st, r = call("POST", "/admin/provision-agents", {"emails": [AGENT_EMAIL], "polling_unit_id": "x"})
    check("provision-agents no token -> 401", st == 401, f"got {st}")
    st, r = call("GET", "/admin/agents")
    check("agents list no token -> 401", st == 401, f"got {st}")
    st, r = call("GET", "/admin/geo/states")
    check("geo/states no token -> 401", st == 401, f"got {st}")
    st, r = call("POST", "/admin/factory-reset", {"admin_password": "x"})
    check("factory-reset no token -> 401", st == 401, f"got {st}")
    st, r = call("GET", "/admin/stats/collation")
    check("stats/collation no token -> 401", st == 401, f"got {st}")
    st, r = call("GET", "/admin/wallet-balance")
    check("wallet-balance no token -> 401", st == 401, f"got {st}")
    st, r = call("GET", "/admin/health")
    check("admin/health no token -> 401", st == 401, f"got {st}")

    # ---------- public read-only API (citizen portal) ----------
    # Must work with NO token, must return aggregates only, and the geo chain
    # must stay walkable — the citizen dashboard depends on all of these.
    st, r = call("GET", "/api/public/stats/collation")
    check("public stats no token -> 200 + aggregate keys",
          st == 200 and set(r.keys()) == {"total_votes", "party_a", "party_b", "party_c",
                                          "verified_percentage", "agents_provisioned", "flagged_count"},
          f"got {st} keys={sorted(r.keys()) if isinstance(r, dict) else 'n/a'}")
    st, r = call("GET", "/api/public/geo/states")
    ok_states = st == 200 and isinstance(r, list) and len(r) > 0
    check("public geo/states no token -> 200 + list", ok_states, f"got {st} states={len(r) if isinstance(r, list) else 0}")
    sid = r[0]["id"] if ok_states else None
    st, r = call("GET", f"/api/public/geo/states/{sid}/lgas")
    ok_lgas = st == 200 and isinstance(r, list)
    check("public geo lgas -> 200", ok_lgas, f"got {st}")
    lid = r[0]["id"] if ok_lgas and r else None
    st, r = call("GET", f"/api/public/geo/lgas/{lid}/wards")
    ok_wards = st == 200 and isinstance(r, list)
    check("public geo wards -> 200", ok_wards, f"got {st}")
    wid = r[0]["id"] if ok_wards and r else None
    st, r = call("GET", f"/api/public/geo/wards/{wid}/pus")
    ok_pus = st == 200 and isinstance(r, list)
    check("public geo pus -> 200 + codes", ok_pus and (not r or "code" in r[0]), f"got {st}")

    # ---------- positive: admin ----------
    st, r = call("GET", "/admin/wallet-balance", headers=AH)
    check("wallet-balance admin -> 200 + address", st == 200 and r.get("address"),
          f"got {st} addr={(r.get('address') or '')[:10]}")
    st, r = call("GET", "/admin/stats/collation", headers=AH)
    check("stats/collation admin -> 200", st == 200, f"got {st}")
    st, r = call("GET", "/admin/geo/states", headers=AH)
    check("geo/states admin -> 200", st == 200 and isinstance(r, list) and len(r) > 0,
          f"got {st} states={len(r) if isinstance(r, list) else 0}")
    st, r = call("POST", "/admin/provision-agents",
                 {"emails": [AGENT_EMAIL], "polling_unit_id": "dbb990f1eef04496bf4f955e83e2ec40"},
                 headers=AH)
    agent_signing_key = (r.get("provisioned") or {}).get(AGENT_EMAIL, {}).get("signing_key")
    check("provision-agents admin -> 200", st == 200 and bool(agent_signing_key), f"got {st} key={'yes' if agent_signing_key else 'NO'}")
    st, r = call("GET", f"/admin/mfa/setup?email={ADMIN_EMAIL}", headers=AH)
    check("mfa/setup self admin -> 200", st == 200 and r.get("secret"), f"got {st}")
    st, r = call("POST", "/admin/factory-reset", {"admin_password": "wrong-password"}, headers=AH)
    check("factory-reset wrong password -> 401", st == 401, f"got {st}")

    # ---------- positive: agent flow ----------
    st, r = call("POST", "/auth/secure-initialization",
                 {"email": AGENT_EMAIL, "new_password": AGENT_PW, "duress_password": "Duress#000x"})
    check("agent secure-init -> 200", st == 200, f"got {st}")
    st, r = call("POST", "/auth/secure-initialization",
                 {"email": AGENT_EMAIL, "new_password": "Again#999x", "duress_password": "Duress#111y"})
    check("secure-init replay blocked -> 403", st == 403, f"got {st}")
    st, r = call("POST", "/auth/login",
                 {"email": AGENT_EMAIL, "password": AGENT_PW, "device_fingerprint": FP})
    agent_tok = r.get("access_token")
    check("agent login -> JWT", bool(agent_tok), f"role={r.get('role')}")
    GH = {"Authorization": f"Bearer {agent_tok}", "X-Device-Fingerprint": FP}

    st, r = call("POST", "/auth/agent/check-in",
                 {"email": AGENT_EMAIL, "latitude": 6.33, "longitude": 5.60}, headers=GH)
    check("agent check-in self -> 200", st == 200, f"got {st}")
    st, r = call("POST", "/auth/agent/check-in",
                 {"email": "victor.odia14@gmail.com", "latitude": 6.33, "longitude": 5.60}, headers=GH)
    check("agent check-in other identity -> 403", st == 403, f"got {st}")
    boundary = "----clTestBoundary42"
    multipart = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="file"; filename="evidence.png"\r\n'
        "Content-Type: image/png\r\n\r\n"
    ).encode() + PNG + f"\r\n--{boundary}--\r\n".encode()
    st, r = call("POST", "/upload/form-ec8a", raw=multipart,
                 headers={"Content-Type": f"multipart/form-data; boundary={boundary}", **GH})
    check("agent upload + fingerprint -> 200", st == 200 and r.get("secure_url"),
          f"got {st}")
    st, r = call("GET", "/admin/wallet-balance", headers=GH)
    check("agent blocked from admin API -> 403", st == 403, f"got {st}")
    st, r = call("GET", f"/admin/mfa/setup?email={ADMIN_EMAIL}", headers=GH)
    check("agent mfa/setup for other -> 403", st == 403, f"got {st}")

    # ---------- mandatory per-agent payload signatures ----------
    st, r = call("POST", "/results/submit",
                 {"pu_code": OCCUPIED_PU, "agent_email": AGENT_EMAIL, "party_a_votes": 1,
                  "party_b_votes": 1, "party_c_votes": 1, "total_valid": 3,
                  "captured_at": "2026-10-08T13:00:00Z"}, headers=GH)
    check("submit unsigned -> 403", st == 403, f"got {st}")
    bad_sig = sign_payload(OCCUPIED_PU, 1, 1, 1, "not-the-agent-key")
    st, r = call("POST", "/results/submit",
                 {"pu_code": OCCUPIED_PU, "agent_email": AGENT_EMAIL, "party_a_votes": 1,
                  "party_b_votes": 1, "party_c_votes": 1, "total_valid": 3,
                  "captured_at": "2026-10-08T13:00:00Z", "signature": bad_sig}, headers=GH)
    check("submit wrong-key signature -> 403", st == 403, f"got {st}")
    good_sig = sign_payload(OCCUPIED_PU, 1, 1, 1, agent_signing_key)
    st, r = call("POST", "/results/submit",
                 {"pu_code": OCCUPIED_PU, "agent_email": AGENT_EMAIL, "party_a_votes": 1,
                  "party_b_votes": 1, "party_c_votes": 1, "total_valid": 3,
                  "captured_at": "2026-10-08T13:00:00Z", "signature": good_sig}, headers=GH)
    check("agent submit full chain -> 409 WORM (regression)", st == 409, f"got {st}")

    # ---------- key rotation ----------
    st, r = call("POST", "/admin/agents/rotate-signing-key", {"email": AGENT_EMAIL}, headers=AH)
    new_key = r.get("signing_key")
    check("admin rotate signing key -> 200 + new key", st == 200 and bool(new_key), f"got {st}")
    old_key_sig = sign_payload(OCCUPIED_PU, 1, 1, 1, agent_signing_key)
    st, r = call("POST", "/results/submit",
                 {"pu_code": OCCUPIED_PU, "agent_email": AGENT_EMAIL, "party_a_votes": 1,
                  "party_b_votes": 1, "party_c_votes": 1, "total_valid": 3,
                  "captured_at": "2026-10-08T13:00:00Z", "signature": old_key_sig}, headers=GH)
    check("rotated-out key signature -> 403", st == 403, f"got {st}")
    new_key_sig = sign_payload(OCCUPIED_PU, 1, 1, 1, new_key)
    st, r = call("POST", "/results/submit",
                 {"pu_code": OCCUPIED_PU, "agent_email": AGENT_EMAIL, "party_a_votes": 1,
                  "party_b_votes": 1, "party_c_votes": 1, "total_valid": 3,
                  "captured_at": "2026-10-08T13:00:00Z", "signature": new_key_sig}, headers=GH)
    check("re-issued key signature -> 409 WORM", st == 409, f"got {st}")

    print()
    print(f"RESULT: {len(passed)} passed, {len(failed)} failed")
    if failed:
        print("FAILED:", ", ".join(failed))
finally:
    sql(f"DELETE FROM users WHERE email IN ('{ADMIN_EMAIL}','{AGENT_EMAIL}');")
    print("cleanup: temp accounts removed")
