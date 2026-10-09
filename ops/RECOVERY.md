# CivicLens Server Recovery

Checklist for rebuilding the stack (and the nightly watchdog) on a fresh
server. Current server: `ubuntu@193.122.220.182` (Ubuntu, Docker).

## 1. Prerequisites

- Docker engine + compose plugin, git
- SSH key authorized for `git@github.com:victorodia/civiclens.git`
- TLS certs are **server state, not in git**: `/etc/letsencrypt/live/193.122.220.182.nip.io/`
  (re-issue with certbot for the new host/nip.io name if the IP changes)

## 2. Code

```bash
git clone git@github.com:victorodia/civiclens.git ~/civiclens
cd ~/civiclens && git checkout hardening   # master == live; hardening is the working branch
```

Branch model: `master` = production, `stable` = permanent pre-hardening
archive (`baseline-2026-10-08`), `hardening` = active work.

## 3. Secrets (`~/civiclens/.env`, gitignored — recreate, never commit)

Required by docker-compose (`:?` guards fail the build if missing):
`DATABASE_URL`, `POSTGRES_PASSWORD`, `JWT_SECRET_KEY`, `POLYGON_RPC_URL`,
`POLYGON_PRIVATE_KEY`. Also used: `POLYGON_PUBLIC_ADDRESS`.

The Postgres password inside `DATABASE_URL` must match what the DB actually
enforces — after a fresh DB init it is the init password; after restoring a
dump it is whatever the dump's server used. Rotate per
`ops/` history (ALTER USER) once reachable.

## 4. Database

Fresh init happens automatically on first `up` (empty `pgdata` volume).

To restore instead, from a dump (`civiclens_baseline_2026-10-08.sql.gz`):
```bash
gunzip -c dump.sql.gz | sudo docker exec -i civiclens-db psql -U civiclens_user -d civiclens
```

Agent `device_signing_key` values live in this DB. Restoring the dump
restores them; a fresh DB means every field agent needs a re-issued key via
`POST /admin/agents/rotate-signing-key`.

## 5. Build & start (note the API-version quirk on this box)

```bash
cd ~/civiclens
sudo DOCKER_API_VERSION=1.52 docker compose build
sudo DOCKER_API_VERSION=1.52 docker compose up -d
```

- After **any** backend container recreate:
  `sudo docker restart civiclens-gateway` — nginx caches upstream IPs at
  startup and serves stale 502s otherwise.
- Never `docker run` the agent container by hand: it must sit on
  `civiclens_civiclens_net` with alias `frontend-agent` or the gateway
  cannot resolve it. Compose does this correctly.
- Health: workers boot in ~15–25s. First `/admin/wallet-balance` call after
  a boot pays a lazy web3 import (up to ~1 min, served in a worker thread —
  API stays up). Verify with:
  `curl -sk https://<host>.nip.io/health`

## 6. Nightly watchdog

```bash
cp ~/civiclens/ops/lockdown_test.py ~/civiclens/ops/lockdown_watchdog.sh \
   ~/civiclens/ops/lockdown_notify.py /home/ubuntu/
# mail credentials — mode 600, never in git
cat > ~/.watchdog_smtp.env <<'EOF'
SMTP_USER=<sender@gmail.com>
SMTP_PASS=<gmail app password>
NOTIFY_TO=<recipient>
EOF
chmod 600 ~/.watchdog_smtp.env
( crontab -l 2>/dev/null | grep -v lockdown_watchdog; \
  echo '17 3 * * * /home/ubuntu/lockdown_watchdog.sh' ) | crontab -
```

Test: `bash /home/ubuntu/lockdown_watchdog.sh` then read
`~/lockdown_last_run.log`. Green nights are silent; red nights email
`NOTIFY_TO` and keep a dated `~/lockdown_failure_*.log`.

## 7. Verify

```bash
python3 /tmp/lockdown_test.py    # or ~/lockdown_test.py — expect "36 passed, 0 failed"
```
