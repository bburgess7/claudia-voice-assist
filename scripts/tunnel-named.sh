#!/usr/bin/env bash
# Stable Cloudflare NAMED tunnel — gives your phone a permanent URL (e.g. https://claudia.example.com)
# so you never re-pair. Requires a ONE-TIME setup (see docs/STABLE-TUNNEL.md); this script just runs
# the tunnel once that's done. Set CLAUDIA_HOSTNAME to your chosen hostname.
set -uo pipefail
PORT="${CLAUDIA_PORT:-4242}"
DAEMON="http://127.0.0.1:$PORT"
HOSTNAME_="${CLAUDIA_HOSTNAME:-}"
TUNNEL="${CLAUDIA_TUNNEL_NAME:-claudia}"

[ -z "$HOSTNAME_" ] && { echo "Set CLAUDIA_HOSTNAME=claudia.yourdomain.com (see docs/STABLE-TUNNEL.md)"; exit 1; }
command -v cloudflared >/dev/null || { echo "brew install cloudflared"; exit 1; }
curl -sf "$DAEMON/health" >/dev/null || { echo "daemon not running: bash scripts/start.sh"; exit 1; }

# ensure a secret + register the STABLE url so the HUD's pairing QR points at it
SECRET=$(curl -s "$DAEMON/config" | python3 -c "import sys,json;print(json.load(sys.stdin).get('shared_secret',''))")
if [ -z "$SECRET" ]; then
  SECRET=$(python3 -c "import secrets;print(secrets.token_urlsafe(18))")
  curl -s -X POST "$DAEMON/config" -H 'Content-Type: application/json' -d "{\"shared_secret\":\"$SECRET\"}" >/dev/null
fi
curl -s -X POST "$DAEMON/config" -H 'Content-Type: application/json' -d "{\"public_url\":\"https://$HOSTNAME_\"}" >/dev/null
echo "Stable tunnel → https://$HOSTNAME_  (pair once via the QR; it won't change). secret: $SECRET"

exec cloudflared tunnel run --url "$DAEMON" "$TUNNEL"
