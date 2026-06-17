#!/usr/bin/env bash
# Claudia one-command setup for a fresh Mac (Apple Silicon). Installs the daemon + the default Kokoro
# voice + CLI. Optional pieces (wake-word listening, Kyutai voice, menu bar) are noted at the end.
#
#   git clone https://github.com/bburgess7/claudia-voice-assist && cd claudia-voice-assist && bash setup.sh
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
say(){ printf "\033[1;31m▸\033[0m %s\n" "$*"; }

# --- prerequisites ---------------------------------------------------------------------------
command -v brew >/dev/null || { echo "Homebrew required: https://brew.sh"; exit 1; }
PY="$(command -v python3.12 || true)"
[ -z "$PY" ] && [ -x /opt/homebrew/bin/python3.12 ] && PY=/opt/homebrew/bin/python3.12
if [ -z "$PY" ]; then say "Installing python@3.12…"; brew install python@3.12; PY=/opt/homebrew/bin/python3.12; fi
command -v ollama >/dev/null || { say "Installing Ollama…"; brew install ollama; }
pgrep -f "ollama serve" >/dev/null || (ollama serve >/dev/null 2>&1 &) ; sleep 2

# --- summarizer model ------------------------------------------------------------------------
say "Pulling the spoken-summarizer model (llama3.2:3b)…"
ollama pull llama3.2:3b

# --- daemon venv (lean, no ML) ---------------------------------------------------------------
say "Creating the daemon environment…"
"$PY" -m venv .venv
./.venv/bin/pip -q install --upgrade pip
./.venv/bin/pip -q install fastapi "uvicorn[standard]" websockets httpx

# --- Kokoro voice sidecar (kokoro-onnx) ------------------------------------------------------
say "Creating the Kokoro voice environment + fetching the model (~340MB)…"
"$PY" -m venv .venv-kokoro
./.venv-kokoro/bin/pip -q install --upgrade pip
./.venv-kokoro/bin/pip -q install kokoro-onnx soundfile numpy
base="https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0"
[ -f .venv-kokoro/kokoro-v1.0.onnx ] || curl -sL -o .venv-kokoro/kokoro-v1.0.onnx "$base/kokoro-v1.0.onnx"
[ -f .venv-kokoro/voices-v1.0.bin ] || curl -sL -o .venv-kokoro/voices-v1.0.bin "$base/voices-v1.0.bin"

# --- CLI on PATH -----------------------------------------------------------------------------
BIN="$(brew --prefix)/bin"
ln -sf "$ROOT/scripts/claudia" "$BIN/claudia"
say "Installed the 'claudia' CLI."

cat <<EOF

  ✅ Claudia is installed.

  Start it:        bash scripts/start.sh        (then open http://127.0.0.1:4242)
  Try it:          claudia say "all set, tests pass — deploy?"

  Optional add-ons:
    • Talk to her (wake word):  bash scripts/setup-listen.sh   then  bash scripts/listen.sh
    • Richer Kyutai voice:      bash scripts/setup-kyutai.sh    then  bash scripts/kyutai.sh
    • Phone access:             bash scripts/tunnel.sh          then tap "Pair a phone"
    • Claude Code narration:    add the Stop/Notification hooks from docs/GLOBAL.md
    • Auto-start at login:      bash scripts/install-launchd.sh
EOF
