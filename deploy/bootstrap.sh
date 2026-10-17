#!/usr/bin/env bash
# ============================================================================
# CivicLens production bootstrap — one run builds a clean prod box from the
# repo. Idempotent: re-running upgrades the deployment in place.
#
#   curl -sSL <raw url>/deploy/bootstrap.sh | sudo bash -s -- \
#       --domain elections.example.org \
#       --smtp-user alerts@gmail.com --smtp-pass '<app password>' \
#       --admin-email boss@example.org
#
# Required: --domain, --smtp-user, --smtp-pass
# Optional: --admin-email/--admin-password (prompted if omitted),
#           --repo, --branch, --ssh-allow, --registry-dump, polygon vars
# ============================================================================
set -euo pipefail

# ----------------------------- configuration ------------------------------
INSTALL_DIR="${INSTALL_DIR:-/opt/civiclens}"
DATA_ROOT="${DATA_ROOT:-/opt/civiclens-data}"
STACK_NAME="${STACK_NAME:-civiclens}"
HTTP_PORT="${HTTP_PORT:-80}"
HTTPS_PORT="${HTTPS_PORT:-443}"
REPO_URL="git@github.com:victorodia/civiclens.git"
BRANCH="master"
DOMAIN="" SMTP_USER="" SMTP_PASS="" NOTIFY_TO=""
ADMIN_EMAIL="" ADMIN_PW=""
SSH_ALLOW=""
REGISTRY_DUMP=""
POLYGON_RPC="" POLYGON_KEY="" POLYGON_ADDR=""

log()  { echo -e "\033[1;34m[bootstrap]\033[0m $*"; }
warn() { echo -e "\033[1;33m[warn]\033[0m $*"; }
die()  { echo -e "\033[1;31m[FAIL]\033[0m $*" >&2; exit 1; }

while [ $# -gt 0 ]; do
    case "$1" in
        --domain)          DOMAIN="$2"; shift 2;;
        --smtp-user)       SMTP_USER="$2"; shift 2;;
        --smtp-pass)       SMTP_PASS="$2"; shift 2;;
        --notify-to)       NOTIFY_TO="$2"; shift 2;;
        --admin-email)     ADMIN_EMAIL="$2"; shift 2;;
        --admin-password)  ADMIN_PW="$2"; shift 2;;
        --repo)            REPO_URL="$2"; shift 2;;
        --branch)          BRANCH="$2"; shift 2;;
        --ssh-allow)       SSH_ALLOW="$2"; shift 2;;
        --registry-dump)   REGISTRY_DUMP="$2"; shift 2;;
        --polygon-rpc)     POLYGON_RPC="$2"; shift 2;;
        --polygon-key)     POLYGON_KEY="$2"; shift 2;;
        --polygon-address) POLYGON_ADDR="$2"; shift 2;;
        -h|--help) grep '^#' "$0" | head -12; exit 0;;
        *) die "unknown argument: $1";;
    esac
done

[ -n "$DOMAIN" ]     || die "--domain is required"
[ -n "$SMTP_USER" ]  || die "--smtp-user is required"
[ -n "$SMTP_PASS" ]  || die "--smtp-pass is required"
NOTIFY_TO="${NOTIFY_TO:-$SMTP_USER}"
[ "$(id -u)" = "0" ] || die "run as root (sudo bash deploy/bootstrap.sh ...)"

# ----------------------------- 1. host hardening ---------------------------
log "hardening host firewall (UFW)"
if ! command -v ufw >/dev/null 2>&1; then apt-get update -qq && apt-get install -y -qq ufw >/dev/null; fi
ufw --force default deny incoming >/dev/null
ufw --force default allow outgoing >/dev/null
if [ -n "$SSH_ALLOW" ]; then
    ufw allow from "$SSH_ALLOW" to any port 22 comment 'SSH (operator)'
else
    ufw allow 22 comment 'SSH'
fi
ufw allow "$HTTP_PORT"  comment 'HTTP (redirect)'
ufw allow "$HTTPS_PORT" comment 'HTTPS'
ufw --force enable >/dev/null
log "UFW enabled: 22$([ -n "$SSH_ALLOW" ] && echo " ($SSH_ALLOW only)") / $HTTP_PORT / $HTTPS_PORT, everything else denied"

log "hardening SSH"
if [ -s "$HOME/.ssh/authorized_keys" ] || [ -s /home/ubuntu/.ssh/authorized_keys ] || [ -s /root/.ssh/authorized_keys ]; then
    sed -i.bak -E 's/^#?[[:space:]]*PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
    sed -i -E 's/^#?[[:space:]]*KbdInteractiveAuthentication.*/KbdInteractiveAuthentication no/' /etc/ssh/sshd_config
    sed -i -E 's/^#?[[:space:]]*PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config
    sshd -t && systemctl reload ssh
    log "SSH: password auth disabled, root login disabled (backup: /etc/ssh/sshd_config.bak)"
else
    warn "no authorized_keys found — SKIPPED sshd hardening (you would lock yourself out)"
fi

log "removing rpcbind (unused RPC portmapper)"
systemctl mask rpcbind rpcbind.socket 2>/dev/null || true

# ----------------------------- 2. docker -----------------------------------
log "installing Docker"
if ! command -v docker >/dev/null 2>&1; then
    apt-get update -qq
    apt-get install -y -qq docker.io >/dev/null
    systemctl enable --now docker
fi
if ! docker compose version >/dev/null 2>&1; then
    apt-get install -y -qq docker-compose-v2 2>/dev/null || \
        curl -sSL https://get.docker.com | sh
fi
log "$(docker --version) / $(docker compose version | head -1)"

# ----------------------------- 3. application ------------------------------
log "installing CivicLens from $REPO_URL (branch $BRANCH)"
mkdir -p "$INSTALL_DIR" "$DATA_ROOT/uploads" "$DATA_ROOT/backups"
chmod 750 "$DATA_ROOT" "$DATA_ROOT/uploads"
if [ -d "$INSTALL_DIR/.git" ]; then
    git -C "$INSTALL_DIR" fetch origin "$BRANCH"
    git -C "$INSTALL_DIR" reset --hard "origin/$BRANCH"
else
    git clone --branch "$BRANCH" --depth 50 "$REPO_URL" "$INSTALL_DIR"
fi

# ---- secrets: fresh on every box, never copied from anywhere ----
PG_PASS=$(openssl rand -hex 24)
JWT_SECRET=$(openssl rand -hex 48)
cat > "$INSTALL_DIR/.env" <<EOF
# Generated by deploy/bootstrap.sh on $(date -u +%FT%TZ) — do not copy between servers.
POSTGRES_PASSWORD=$PG_PASS
DATABASE_URL=postgresql+asyncpg://civiclens_user:$PG_PASS@db:5432/civiclens
JWT_SECRET_KEY=$JWT_SECRET
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=$SMTP_USER
SMTP_PASS=$SMTP_PASS
NOTIFY_TO=$NOTIFY_TO
POLYGON_RPC_URL=${POLYGON_RPC:-https://polygon-rpc.com}
POLYGON_PRIVATE_KEY=${POLYGON_KEY:-unset}
POLYGON_PUBLIC_ADDRESS=${POLYGON_ADDR:-unset}
GEOFENCE_RADIUS_METRES=400
EOF
chmod 600 "$INSTALL_DIR/.env"
[ -n "$POLYGON_KEY" ] || warn "POLYGON_PRIVATE_KEY not supplied — on-chain anchoring will not work until set in $INSTALL_DIR/.env"

# ---- watchdog SMTP credentials (host-side alerting only) ----
cat > "$DATA_ROOT/.watchdog_smtp.env" <<EOF
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=$SMTP_USER
SMTP_PASS=$SMTP_PASS
NOTIFY_TO=$NOTIFY_TO
EOF
chmod 600 "$DATA_ROOT/.watchdog_smtp.env"

# ---- gateway config with the real domain baked in ----
sed "s/__DOMAIN__/$DOMAIN/g" "$INSTALL_DIR/deploy/gateway_prod.conf" \
    > "$INSTALL_DIR/deploy/gateway_nginx.rendered.conf"

# ---- stack up ----
log "building and starting the stack (this takes a few minutes the first time)"
cd "$INSTALL_DIR"
export STACK_NAME DATA_ROOT HTTP_PORT HTTPS_PORT
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build

log "waiting for backend health"
for i in $(seq 1 60); do
    if curl -sk "https://127.0.0.1:${HTTPS_PORT}/health" >/dev/null 2>&1 || \
       curl -s  "http://127.0.0.1:${HTTP_PORT}/health"  >/dev/null 2>&1; then
        log "backend healthy after ${i}0s"; break
    fi
    [ "$i" = "60" ] && die "backend did not become healthy in 10 minutes — check: docker compose -f docker-compose.yml -f docker-compose.prod.yml logs backend"
    sleep 10
done

# ----------------------------- 4. TLS --------------------------------------
if [ ! -d "/etc/letsencrypt/live/$DOMAIN" ]; then
    log "obtaining TLS certificate for $DOMAIN (gateway paused briefly)"
    bash "$INSTALL_DIR/deploy/get-certs.sh" "$DOMAIN" "$SMTP_USER"
fi
docker restart "${STACK_NAME}-gateway" >/dev/null

# ----------------------------- 5. platform admin ---------------------------
if [ -z "$ADMIN_EMAIL" ]; then read -r -p "Platform admin email: " ADMIN_EMAIL; fi
[ -n "$ADMIN_EMAIL" ] || die "admin email required"
if [ -z "$ADMIN_PW" ]; then
    read -r -s -p "Platform admin password (min 12 chars): " ADMIN_PW; echo
fi
[ "${#ADMIN_PW}" -ge 12 ] || die "admin password must be at least 12 characters"
ADMIN_ID="platform-admin-$(openssl rand -hex 8)"
docker exec -i "${STACK_NAME}-backend" python3 - "$ADMIN_ID" "$ADMIN_EMAIL" "$ADMIN_PW" <<'PYEOF'
import asyncio, sys
from app.db import AsyncSessionLocal
from app.models import User
from app.security import get_password_hash

async def main():
    async with AsyncSessionLocal() as s:
        u = User(id=sys.argv[1], email=sys.argv[2], full_name="Platform Administrator",
                 hashed_password=get_password_hash(sys.argv[3]), role="admin",
                 is_active=True, requires_password_reset=True,
                 device_fingerprint="ADMIN_TRUSTED_DEVICE")
        s.add(u)
        await s.commit()
        print("admin created:", sys.argv[2])

asyncio.run(main())
PYEOF

# ----------------------------- 6. INEC registry (optional) -----------------
if [ -n "$REGISTRY_DUMP" ]; then
    log "restoring INEC registry from $REGISTRY_DUMP"
    case "$REGISTRY_DUMP" in
        *.gz) gunzip -c "$REGISTRY_DUMP" | docker exec -i "${STACK_NAME}-db" psql -U civiclens_user -d civiclens -q ;;
        *)    cat "$REGISTRY_DUMP"        | docker exec -i "${STACK_NAME}-db" psql -U civiclens_user -d civiclens -q ;;
    esac
    log "registry restore complete"
else
    warn "no --registry-dump supplied — load the INEC registry separately:"
    warn "  test VM:  sudo docker exec civiclens-db pg_dump -U civiclens_user -d civiclens -t states -t lgas -t wards -t polling_units | gzip > registry.sql.gz"
    warn "  then:     $0 ... --registry-dump /path/registry.sql.gz"
fi

# ----------------------------- 7. watchdogs --------------------------------
log "installing nightly watchdog cron entries"
ENV_PREFIX="CL_BASE=$INSTALL_DIR CL_DATA=$DATA_ROOT/uploads CL_BACKUP=$DATA_ROOT/backups CL_LOG_DIR=$DATA_ROOT CL_NOTIFY=$INSTALL_DIR/ops/lockdown_notify.py CL_WATCHDOG_ENV=$DATA_ROOT/.watchdog_smtp.env BACKEND_CONTAINER=${STACK_NAME}-backend DB_CONTAINER=${STACK_NAME}-db"
(crontab -l 2>/dev/null | grep -v -E 'lockdown_watchdog|audit_chain_watchdog|backup_watchdog'; cat <<EOF
17 3 * * * $INSTALL_DIR/ops/lockdown_watchdog.sh
23 3 * * * $ENV_PREFIX $INSTALL_DIR/ops/audit_chain_watchdog.sh
47 3 * * * $ENV_PREFIX $INSTALL_DIR/ops/backup_watchdog.sh
EOF
) | crontab -
log "cron installed: lockdown 03:17 / audit chain 03:23 / backup 03:47 (UTC)"

# ----------------------------- 8. smoke test -------------------------------
log "running smoke test"
sleep 5
HEALTH=$(curl -sk "https://127.0.0.1:${HTTPS_PORT}/health" || curl -s "http://127.0.0.1:${HTTP_PORT}/health")
echo "$HEALTH" | grep -q '"status"\|healthy\|ok' && log "health endpoint OK" || warn "health endpoint returned: $HEALTH"
ST=$(curl -sk -o /dev/null -w '%{http_code}' -X POST "https://127.0.0.1:${HTTPS_PORT}/auth/login" \
        -H 'Content-Type: application/json' -d '{"email":"nobody@example.org","password":"x"}')
[ "$ST" = "401" ] && log "auth endpoint rejects bad login (401)" || warn "unexpected login probe status: $ST"

log "============================================================"
log " CivicLens production is up at https://$DOMAIN"
log "   app dir:    $INSTALL_DIR"
log "   data dir:   $DATA_ROOT (uploads + backups + watchdog env)"
log "   admin:      $ADMIN_EMAIL (must change password at first login)"
log "   stack:      docker compose -f docker-compose.yml -f docker-compose.prod.yml"
log " Next: point DNS at this host, then run the lockdown suite:"
log "   python3 $INSTALL_DIR/ops/lockdown_test.py"
log "============================================================"
