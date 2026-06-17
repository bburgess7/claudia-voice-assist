#!/usr/bin/env bash
# Start Claudia's ears (wake-word conversational loop). Optional sidecar.
# Requires mic permission for the terminal running it (System Settings > Privacy > Microphone).
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec "$ROOT/.venv-listen/bin/python" "$ROOT/listen/listen.py"
