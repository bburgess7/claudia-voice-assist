#!/usr/bin/env bash
# Install + launch Claudia's menu-bar app (rumps). Gives you an always-visible on/off + mute + status.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"; cd "$ROOT"
PY="${PY:-/opt/homebrew/bin/python3.12}"
[ -d menubar/.venv ] || "$PY" -m venv menubar/.venv
./menubar/.venv/bin/pip -q install --upgrade pip >/dev/null
./menubar/.venv/bin/pip -q install rumps >/dev/null
pkill -f "claudia_menubar.py" 2>/dev/null || true
nohup ./menubar/.venv/bin/python menubar/claudia_menubar.py >"$HOME/.claudia/logs/menubar.log" 2>&1 &
echo "✅ Claudia menu-bar app launched — look for ◉ in your menu bar (top-right)."
