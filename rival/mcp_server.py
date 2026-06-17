#!/usr/bin/env python3
"""Claudia MCP server — exposes Claudia's capabilities as standard MCP tools over stdio.

This is the portability + extensibility layer (Goal 2). Any MCP client can now drive Claudia:
Claude Code, Cursor, or a Rival.io agent (Rival speaks MCP / JSON-RPC 2.0). The tools are thin
wrappers over the local daemon's HTTP API, so the voice stays local while the *control surface*
becomes portable.

Stdlib only (no mcp SDK) — implements the minimal JSON-RPC: initialize, tools/list, tools/call.
Register with Claude Code:
  claude mcp add claudia -- /usr/bin/python3 /Users/benburgess/dev/claudia-voice-assist/rival/mcp_server.py
"""
import json
import os
import sys
import urllib.request

DAEMON = os.environ.get("CLAUDIA_URL", "http://127.0.0.1:4242")


def _daemon(path, payload=None, method="POST"):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(DAEMON + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


TOOLS = [
    {
        "name": "claudia_speak",
        "description": "Speak text aloud through Claudia. Use mode to control how much is read: "
                       "'summary' (default, only the gist), 'headline' (one sentence), or 'verbatim'.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "What to say."},
                "mode": {"type": "string", "enum": ["summary", "headline", "verbatim"]},
            },
            "required": ["text"],
        },
    },
    {
        "name": "claudia_stop",
        "description": "Immediately stop and clear any in-progress or queued speech (barge-in).",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "claudia_set_rate",
        "description": "Set Claudia's speaking rate. 1.0 is normal; 0.5 slow, 2.0 fast.",
        "inputSchema": {"type": "object",
                        "properties": {"rate": {"type": "number"}}, "required": ["rate"]},
    },
    {
        "name": "claudia_set_voice",
        "description": "Set Claudia's voice by id (see claudia_status for options).",
        "inputSchema": {"type": "object",
                        "properties": {"voice": {"type": "string"}}, "required": ["voice"]},
    },
    {
        "name": "claudia_status",
        "description": "Get Claudia's current config (engine, voice, rate, verbosity, muted) and "
                       "the available voices.",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


def call_tool(name, args):
    if name == "claudia_speak":
        r = _daemon("/speak", {"text": args.get("text", ""), "mode": args.get("mode")})
        return f"Speaking: {r.get('spoken', '')}"
    if name == "claudia_stop":
        _daemon("/stop", {})
        return "Stopped."
    if name == "claudia_set_rate":
        r = _daemon("/config", {"rate": float(args["rate"])})
        return f"Rate set to {r.get('rate')}."
    if name == "claudia_set_voice":
        r = _daemon("/config", {"voice": args["voice"]})
        return f"Voice set to {r.get('voice')}."
    if name == "claudia_status":
        cfg = _daemon("/config", method="GET")
        voices = _daemon("/voices", method="GET").get("voices", [])
        cfg["available_voices"] = [v["id"] for v in voices]
        return json.dumps(cfg, indent=2)
    raise ValueError(f"unknown tool {name}")


def send(obj):
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        mid, method, params = msg.get("id"), msg.get("method"), msg.get("params", {})

        if method == "initialize":
            send({"jsonrpc": "2.0", "id": mid, "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "claudia", "version": "1.0.0"}}})
        elif method == "notifications/initialized":
            continue
        elif method == "tools/list":
            send({"jsonrpc": "2.0", "id": mid, "result": {"tools": TOOLS}})
        elif method == "tools/call":
            name = params.get("name")
            args = params.get("arguments", {})
            try:
                text = call_tool(name, args)
                send({"jsonrpc": "2.0", "id": mid,
                      "result": {"content": [{"type": "text", "text": text}]}})
            except Exception as e:
                send({"jsonrpc": "2.0", "id": mid,
                      "result": {"content": [{"type": "text", "text": f"error: {e}"}],
                                 "isError": True}})
        elif mid is not None:
            send({"jsonrpc": "2.0", "id": mid,
                  "error": {"code": -32601, "message": f"method not found: {method}"}})


if __name__ == "__main__":
    main()
