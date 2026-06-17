#!/usr/bin/env bash
# Expose the local Claudia daemon via a Cloudflare quick tunnel so the hosted control panel (on your
# phone) can reach it — no Tailscale. Ensures a shared secret, then REGISTERS the public URL with the
# daemon so the Mac HUD shows a "scan to pair" QR — the phone just scans it (no typing, no jargon).
#
# Quick tunnels are ephemeral. For a STABLE phone link, use scripts/tunnel-named.sh (a Cloudflare
# named tunnel on your own domain) instead.
set -uo pipefail
PORT="${CLAUDIA_PORT:-4242}"
DAEMON="http://127.0.0.1:$PORT"

command -v cloudflared >/dev/null || { echo "cloudflared not installed (brew install cloudflared)"; exit 1; }
curl -sf "$DAEMON/health" >/dev/null || { echo "daemon not running — start it: bash scripts/start.sh"; exit 1; }

# ensure a shared secret exists (generate one if empty)
SECRET=$(curl -s "$DAEMON/config" | python3 -c "import sys,json;print(json.load(sys.stdin).get('shared_secret',''))")
if [ -z "$SECRET" ]; then
  SECRET=$(python3 -c "import secrets;print(secrets.token_urlsafe(18))")
  curl -s -X POST "$DAEMON/config" -H 'Content-Type: application/json' -d "{\"shared_secret\":\"$SECRET\"}" >/dev/null
fi

LOG=$(mktemp)
cleanup(){ curl -s -X POST "$DAEMON/config" -H 'Content-Type: application/json' -d '{"public_url":""}' >/dev/null 2>&1; rm -f "$LOG"; }
trap cleanup EXIT INT TERM

echo "Starting tunnel… the pairing QR will appear in the control panel on your Mac."
cloudflared tunnel --url "$DAEMON" >"$LOG" 2>&1 &
CF_PID=$!

# watch for the public URL, then register it with the daemon (HUD renders the QR from it)
for i in $(seq 1 40); do
  URL=$(grep -oE "https://[a-z0-9-]+\.trycloudflare\.com" "$LOG" 2>/dev/null | head -1)
  if [ -n "$URL" ]; then
    curl -s -X POST "$DAEMON/config" -H 'Content-Type: application/json' -d "{\"public_url\":\"$URL\"}" >/dev/null
    echo "────────────────────────────────────────────────────────"
    echo "  Tunnel live: $URL"
    echo "  On your Mac, open the control panel ($DAEMON) and tap 'Pair a phone' —"
    echo "  then scan the QR with your phone's camera. That's it."
    echo "  (Manual fallback — URL: $URL  secret: $SECRET)"
    echo "────────────────────────────────────────────────────────"
    break
  fi
  sleep 1
done

wait "$CF_PID"
