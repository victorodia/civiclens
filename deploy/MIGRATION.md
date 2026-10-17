# CivicLens Production Migration Runbook

Test-to-production cutover sequence. The current VM stays alive as the
staging environment; production is built clean from the repo.

## 0. Before you start (on the test VM)

- Land the pentest remediations first: upload content validation, login
  rate limiting/uniform timing, geofence decision. Prod must not inherit
  known holes.
- Export the INEC registry (it is too slow to re-scrape):

  ```bash
  sudo docker exec civiclens-db pg_dump -U civiclens_user -d civiclens \
      -t states -t lgas -t wards -t polling_units | gzip > registry_$(date -u +%Y%m%d).sql.gz
  ```

- Decide the production domain name and register it.

## 1. Provision the production VM

- OCI flexible shape: **4 vCPU / 16 GB RAM / 100+ GB SSD** (upsizable for
  election week).
- Ubuntu 24.04. Add **your SSH public key at creation time** (bootstrap
  disables password auth; without a key it skips that step and warns).
- Attach a separate block volume for `/opt/civiclens-data` if available.

## 2. Run the bootstrap (as root)

```bash
curl -sSL https://raw.githubusercontent.com/victorodia/civiclens/master/deploy/bootstrap.sh | sudo bash -s -- \
    --domain elections.yourdomain.org \
    --smtp-user octofotingroup@gmail.com --smtp-pass '<app password>' \
    --admin-email you@yourdomain.org \
    --ssh-allow YOUR.HOME.IP/32 \
    --registry-dump /path/registry_YYYYMMDD.sql.gz
```

The script: hardens UFW/SSH, removes rpcbind, installs Docker, clones the
repo to `/opt/civiclens`, generates **fresh** DB + JWT secrets, renders the
gateway config, builds and starts the stack, obtains TLS certificates,
creates the platform admin (password change forced at first login), loads
the registry dump, and installs the three nightly watchdog cron entries.

Re-running the script upgrades in place (git pull + rebuild); it never
reuses secrets across boxes.

## 3. DNS cutover

1. In your DNS panel, point the domain at the new VM.
2. **Before certificates exist**, keep any CDN proxy disabled (grey cloud in
   Cloudflare) — the bootstrap's standalone certbot needs direct port 80.
3. After the stack verifies, enable Cloudflare proxying and then restrict
   the origin firewall to Cloudflare IP ranges only (UFW rules on 80/443).

## 4. Data sync (clients, elections, agents, results)

The registry ships with `--registry-dump`. Operational data (real clients,
elections, agent accounts) should be **recreated through the admin portal**
on production rather than copied row-by-row — agent passwords are Argon2
hashes and portable, but signing keys and device fingerprints belong to
specific deployments. If a bulk copy is ever needed, use `pg_dump` of the
full database during a maintenance window and re-issue all agent signing
keys afterwards via **Rotate Signing Key**.

## 5. Verify production

```bash
cd /opt/civiclens
python3 ops/lockdown_test.py          # expect 56 passed, 0 failed
sudo docker exec civiclens-backend python3 /tmp/audit_chain_check.py  # VALID
```

Then: log in as the platform admin, create one test client + election +
agent, walk the full agent flow (secure-init, login, verify entry, ping,
submit), and confirm the result appears in the document feed.

## 6. Election-week posture

- Upsize the VM shape 1-2 weeks before election day.
- `sudo docker exec civiclens-db pg_dump ... | gzip` manual backup the
  night before; verify a scratch restore (see ops/backup_watchdog.sh).
- Take an OCI VM snapshot the night before.
- Keep the test VM running as instant rollback and staging.

## Layout on production

```
/opt/civiclens            app (git clone)
/opt/civiclens-data/uploads    evidence files
/opt/civiclens-data/backups    nightly dumps (14-day retention)
/opt/civiclens-data/.watchdog_smtp.env   alert credentials (chmod 600)
/etc/letsencrypt         TLS certificates
```

Stack control: `docker compose -f docker-compose.yml -f docker-compose.prod.yml`
