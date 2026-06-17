#!/usr/bin/env bash
# Install + launch Claudia's global push-to-talk hotkey (HOLD = talk, DOUBLE-TAP = conversation).
# Reuses the listen venv (it already has sounddevice); just adds pynput.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"; cd "$ROOT"
[ -x "$ROOT/.venv-listen/bin/python" ] || { echo "Run scripts/setup-listen.sh first (needs the mic/STT venv)."; exit 1; }
./.venv-listen/bin/python -m pip -q install pynput pyobjc-framework-Cocoa pyobjc-framework-Quartz >/dev/null
pkill -f "talk_hotkey.py" 2>/dev/null || true
nohup ./.venv-listen/bin/python hotkey/talk_hotkey.py >"$HOME/.claudia/logs/hotkey.log" 2>&1 &
echo "✅ Hotkey daemon launched. Default key: RIGHT COMMAND (⌘)."
echo "   • HOLD ⌘ to talk, release to send."
echo "   • DOUBLE-TAP ⌘ to toggle hands-free conversation."
echo ""
echo "⚠️  First time: grant Accessibility permission to your terminal app, or the keys won't register."
echo "   Opening that settings pane now — add/enable your terminal, then re-run this script."
open "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility" 2>/dev/null || true
