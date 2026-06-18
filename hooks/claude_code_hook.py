#!/usr/bin/env python3
"""Claude Code -> Claudia bridge.

Register in ~/.claude/settings.json so Claudia narrates a SPOKEN SUMMARY of what Claude Code did
(decisions, results, questions) instead of reading raw code. Fails silent if the daemon is down so
it never blocks or slows Claude Code.

Handled events:
  Stop          -> speak a summary of Claude's final message for this turn
  Notification  -> speak the notification (e.g. "Claude needs permission to run npm test")

settings.json:
  "hooks": {
    "Stop":         [{"hooks": [{"type": "command", "command": "python3 ~/dev/claudia/hooks/claude_code_hook.py"}]}],
    "Notification": [{"hooks": [{"type": "command", "command": "python3 ~/dev/claudia/hooks/claude_code_hook.py"}]}]
  }
"""
import json
import os
import sys
import urllib.request

DAEMON = os.environ.get("CLAUDIA_URL", "http://127.0.0.1:4242")


def post(path, payload):
    try:
        req = urllib.request.Request(
            DAEMON + path, data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=2)
    except Exception:
        pass  # daemon down or busy — never block Claude Code


def last_assistant_text(transcript_path):
    """Pull the text of the final assistant message from a Claude Code JSONL transcript."""
    if not transcript_path or not os.path.exists(transcript_path):
        return ""
    text = ""
    try:
        with open(transcript_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if row.get("type") != "assistant":
                    continue
                msg = row.get("message", {})
                parts = msg.get("content", [])
                if isinstance(parts, str):
                    text = parts
                    continue
                chunk = " ".join(
                    p.get("text", "") for p in parts
                    if isinstance(p, dict) and p.get("type") == "text")
                if chunk.strip():
                    text = chunk  # keep last non-empty assistant text
    except OSError:
        return ""
    return text.strip()


def project_name(data):
    """Which project/terminal fired this hook, from the session's working directory."""
    cwd = (data.get("cwd") or "").rstrip("/")
    if cwd:
        return os.path.basename(cwd)
    # fallback: ~/.claude/projects/<encoded-cwd>/<session>.jsonl  (cwd with / replaced by -)
    enc = os.path.basename(os.path.dirname(data.get("transcript_path") or ""))
    if not enc:
        return ""
    for root in ("-dev-", "-tools-", "-Projects-", "-Downloads-"):   # repo roots -> keep the tail
        if root in enc:
            return enc.split(root, 1)[1]
    return enc.rstrip("-").split("-")[-1]


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return
    event = data.get("hook_event_name", "")
    project = project_name(data)

    if event == "Notification":
        msg = data.get("message", "").strip()
        if msg:  # speak the notice as-is (don't reword a short, already-clean message)
            post("/speak", {"text": msg, "mode": "verbatim", "prefix": project})
        return

    if event == "Stop":
        text = last_assistant_text(data.get("transcript_path", ""))
        if text:
            post("/speak", {"text": text, "mode": "summary", "prefix": project})
        return


if __name__ == "__main__":
    main()
