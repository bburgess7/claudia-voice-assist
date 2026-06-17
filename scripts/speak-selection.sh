#!/usr/bin/env bash
# Speak the current clipboard aloud through Claudia — the "speak from any app" hook.
# Bind this to a global hotkey via macOS Shortcuts (see docs/GLOBAL.md):
#   1. Copy text in any app (Cmd-C)
#   2. Press your hotkey -> Claudia reads it
# Uses `read` mode (verbatim, lightly cleaned). Use `summary` to summarize long selections instead.
MODE="${1:-read}"
TEXT="$(pbpaste)"
[ -z "$TEXT" ] && exit 0
if [ "$MODE" = "summary" ]; then
  printf '%s' "$TEXT" | /opt/homebrew/bin/claudia say
else
  printf '%s' "$TEXT" | /opt/homebrew/bin/claudia read
fi
