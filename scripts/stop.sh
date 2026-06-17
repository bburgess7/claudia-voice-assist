#!/usr/bin/env bash
# Stop Claudia (daemon + sidecar).
pkill -f "uvicorn daemon.server:app" 2>/dev/null || true
[ -f "$HOME/.claudia/kokoro.pid" ] && kill "$(cat "$HOME/.claudia/kokoro.pid")" 2>/dev/null || true
pkill -f "engines_sidecar/kokoro_server.py" 2>/dev/null || true
echo "[claudia] stopped"
