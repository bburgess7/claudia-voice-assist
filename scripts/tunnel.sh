#!/usr/bin/env bash
# Expose the local Claudia daemon to the internet via a Cloudflare quick tunnel, so the Vercel-hosted
# control panel (on your phone) can reach it — no Tailscale needed. Ensures a shared secret is set
# first, then prints the tunnel URL + secret to paste into the phone's connect screen.
#
# Quick tunnels are ephemeral (new URL each run, no account needed). For a STABLE URL, set up a named
# tunnel against one of your domains: see https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/
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
  echo "Generated a shared secret."
fi

echo "────────────────────────────────────────────────────────"
echo " Starting Cloudflare tunnel to $DAEMON ..."
echo " When the https://...trycloudflare.com URL appears below:"
echo "   1. Open the control panel on your phone: the Vercel URL"
echo "   2. On its connect screen, paste:"
echo "        Daemon URL : <the trycloudflare URL>"
echo "        Secret     : $SECRET"
echo "────────────────────────────────────────────────────────"
exec cloudflared tunnel --url "$DAEMON"
