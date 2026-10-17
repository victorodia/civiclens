#!/usr/bin/env bash
# Obtain/renew a Let's Encrypt certificate via the standalone authenticator.
# The gateway container holds ports 80/443, so it is paused for the ~5 seconds
# issuance takes, then restarted. Usage: get-certs.sh <domain> <email>
set -euo pipefail
DOMAIN="$1"
EMAIL="$2"
[ "$(id -u)" = "0" ] || { echo "run as root"; exit 1; }

if ! command -v certbot >/dev/null 2>&1; then
    apt-get update -qq && apt-get install -y -qq certbot >/dev/null
fi

GW=""
for c in $(docker ps --format '{{.Names}}' | grep gateway); do GW="$c"; done
[ -n "$GW" ] && docker stop "$GW" >/dev/null
trap '[ -n "$GW" ] && docker start "$GW" >/dev/null' EXIT

certbot certonly --standalone --non-interactive --agree-tos \
    -m "$EMAIL" -d "$DOMAIN" \
    --keep-until-expiring --expand

echo "certificate ready: /etc/letsencrypt/live/$DOMAIN"
