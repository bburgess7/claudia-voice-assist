#!/usr/bin/env bash
# Start Claudia: the Kokoro sidecar (its own venv) + claudiad (lean daemon).
# Bind host: 127.0.0.1 by default (local only). Set CLAUDIA_HOST=0.0.0.0 to reach it over Tailscale.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

HOST="${CLAUDIA_HOST:-127.0.0.1}"
PORT="${CLAUDIA_PORT:-4242}"
KOKORO_PORT="${CLAUDIA_KOKORO_PORT:-4243}"
LOGDIR="$HOME/.claudia/logs"; mkdir -p "$LOGDIR"

echo "[claudia] starting Kokoro sidecar on :$KOKORO_PORT ..."
CLAUDIA_KOKORO_PORT="$KOKORO_PORT" "$ROOT/.venv-kokoro/bin/python" \
  "$ROOT/engines_sidecar/kokoro_server.py" >"$LOGDIR/kokoro.log" 2>&1 &
echo $! > "$HOME/.claudia/kokoro.pid"

# wait for the sidecar to load its model
for i in $(seq 1 60); do
  if curl -sf "http://127.0.0.1:$KOKORO_PORT/health" >/dev/null 2>&1; then
    echo "[claudia] sidecar ready"; break; fi
  sleep 1
done

echo "[claudia] starting daemon on $HOST:$PORT ..."
exec "$ROOT/.venv/bin/uvicorn" daemon.server:app --host "$HOST" --port "$PORT" --log-level warning
