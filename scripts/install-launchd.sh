#!/usr/bin/env bash
# Install Claudia as a launchd service so it starts at login and stays up.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLIST="$HOME/Library/LaunchAgents/com.ben.claudia.plist"
mkdir -p "$HOME/Library/LaunchAgents" "$HOME/.claudia/logs"
sed -e "s#__ROOT__#$ROOT#g" -e "s#__HOME__#$HOME#g" "$ROOT/scripts/com.ben.claudia.plist" > "$PLIST"
launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"
echo "[claudia] launchd service installed and loaded ($PLIST)"
echo "          stop:    launchctl unload $PLIST"
echo "          logs:    ~/.claudia/logs/"
