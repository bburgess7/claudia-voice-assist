#!/usr/bin/env bash
# Set up the wake-word listening sidecar (.venv-listen). Then run scripts/listen.sh and say "hey claudia".
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"; cd "$ROOT"
PY="${PY:-/opt/homebrew/bin/python3.12}"
"$PY" -m venv .venv-listen
./.venv-listen/bin/pip -q install --upgrade pip
./.venv-listen/bin/pip -q install openwakeword sounddevice faster-whisper numpy
echo "✅ listen ready. Grant mic permission, then: bash scripts/listen.sh"
