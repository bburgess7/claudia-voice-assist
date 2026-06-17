#!/usr/bin/env bash
# Start the Kyutai TTS sidecar (lowest-latency conversational voice). Optional / opt-in: it loads a
# ~2-3GB model, so it's separate from the default start.sh. Once it's up, pick "Kyutai" in the control
# panel (or `claudia engine kyutai`). First run downloads the model.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${CLAUDIA_KYUTAI_PORT:-4244}"
LOGDIR="$HOME/.claudia/logs"; mkdir -p "$LOGDIR"
echo "[kyutai] starting sidecar on :$PORT (first run downloads the model; watch $LOGDIR/kyutai.log)"
HF_HUB_DISABLE_XET=1 CLAUDIA_KYUTAI_PORT="$PORT" \
  exec "$ROOT/.venv-kyutai/bin/python" "$ROOT/engines_sidecar/kyutai_server.py"
