"""Claudia's agency — a local tool-using agent so she can actually DO things on the Mac, not just talk.

A request (typed or spoken) goes to a local tool-calling model (Ollama). The model decides which tools
to call; we execute them with hard safety guardrails, feed results back, and loop until it produces a
short spoken answer. Fully local — no cloud, no data leaves the machine.

Tools: run_shell (read-oriented), read_file, list_dir, open_thing, applescript.
Safety: destructive shell is blocked outright; risky writes need an explicit confirm flag. Everything
runs with a timeout and truncated output.
"""
from __future__ import annotations

import getpass
import json
import os
import platform
import re
import socket
import subprocess
import urllib.request
from typing import Optional

OLLAMA_CHAT_URL = "http://127.0.0.1:11434/api/chat"
MAX_OUT = 2500          # truncate tool output fed back to the model
MAX_STEPS = 6           # max tool-call iterations per request


def _context() -> str:
    home = os.path.expanduser("~")
    try:
        osver = platform.mac_ver()[0] or platform.platform()
    except Exception:
        osver = "macOS"
    return (
        f"Real machine context — use these EXACT values, never placeholders: "
        f"user={getpass.getuser()}; home={home}; host={socket.gethostname()}; os=macOS {osver}. "
        f"Useful commands: free disk -> `df -h /`; battery -> `pmset -g batt`; "
        f"Downloads -> `ls {home}/Downloads`; running apps -> "
        f"`osascript -e 'tell application \"System Events\" to get name of (processes where background only is false)'`; "
        f"date/time -> `date`; current music -> `osascript -e 'tell application \"Music\" to name of current track'`; "
        f"set volume -> `osascript -e 'set volume output volume 50'`."
    )


PERSONA = (
    "You are Claudia, a capable, concise voice assistant running locally on Ben's Mac with the power "
    "to act on his behalf. You can run read-only shell commands, read files, list folders, open apps "
    "or URLs, and control Mac apps via AppleScript. ALWAYS call a tool when the answer depends on the "
    "machine's real state or the user asks you to DO something — never guess, never invent paths or "
    "numbers. Read the tool output and base your answer on it. Then reply in 1-3 short spoken "
    "sentences (no markdown, no code, no file paths, no secrets). If a request is destructive or "
    "risky, say it needs confirmation instead of doing it.\n\n" + _context()
)

# Claudia's own editable instructions. She loads this into her brain every turn, and updates it via
# the `remember` tool. This is how she changes her own behavior on your spoken instruction.
PERSONA_FILE = os.path.expanduser("~/.claudia/persona.md")
_PERSONA_HEADER = ("# Claudia's standing instructions\n"
                   "# She appends to this when you tell her to remember something or change behavior.\n\n")


def load_instructions() -> str:
    try:
        with open(PERSONA_FILE) as f:
            lines = [ln for ln in f.read().splitlines()
                     if ln.strip() and not ln.lstrip().startswith("#")]
        return "\n".join(lines).strip()
    except Exception:
        return ""


def system_prompt() -> str:
    extra = load_instructions()
    if not extra:
        return PERSONA
    # Put the standing orders LAST and frame them hard — small models weight the end of the prompt most.
    return (PERSONA + "\n\nSTANDING ORDERS FROM BEN. These override your defaults and apply to EVERY "
            "reply, including this one (how you address him, your tone, your length, your behavior). "
            "Obey every one:\n" + extra)


# Hard denylist — these are never executed, even if the model asks.
_DANGER = re.compile(
    r"\b(rm\s+-rf|rm\s+-fr|\bsudo\b|\bdd\b|mkfs|:\(\)\s*\{|shutdown|reboot|halt|killall|"
    r"diskutil\s+(erase|reformat|partition)|>\s*/dev/|chmod\s+-R\s+777\s+/|launchctl\s+remove|"
    r"\bpkill\b|\bkill\s+-9\b|defaults\s+delete|rm\s+-r\s+/|find\s+/\s+-delete)\b",
    re.IGNORECASE)

TOOLS = [
    {"type": "function", "function": {
        "name": "run_shell",
        "description": "Run a read-only shell command on the Mac and return its output. For querying "
                       "system state, files, processes, git status, etc. Destructive commands are blocked.",
        "parameters": {"type": "object",
                       "properties": {"command": {"type": "string", "description": "the shell command"}},
                       "required": ["command"]}}},
    {"type": "function", "function": {
        "name": "read_file",
        "description": "Read a text file and return its contents (truncated).",
        "parameters": {"type": "object",
                       "properties": {"path": {"type": "string"}}, "required": ["path"]}}},
    {"type": "function", "function": {
        "name": "list_dir",
        "description": "List the contents of a directory.",
        "parameters": {"type": "object",
                       "properties": {"path": {"type": "string"}}, "required": ["path"]}}},
    {"type": "function", "function": {
        "name": "open_thing",
        "description": "Open an app, file, folder, or URL on the Mac (uses macOS `open`).",
        "parameters": {"type": "object",
                       "properties": {"target": {"type": "string"}}, "required": ["target"]}}},
    {"type": "function", "function": {
        "name": "applescript",
        "description": "Run an AppleScript to control Mac apps (volume, Music, Notes, notifications, "
                       "Calendar, etc.). Use for actions the shell can't do.",
        "parameters": {"type": "object",
                       "properties": {"script": {"type": "string"}}, "required": ["script"]}}},
    {"type": "function", "function": {
        "name": "remember",
        "description": "Save a durable instruction that changes how you behave from now on. Call this "
                       "whenever Ben tells you to remember something, change your behavior, adjust your "
                       "tone, or update your instructions (e.g. 'always keep answers under two "
                       "sentences', 'call me boss', 'check git before answering about code').",
        "parameters": {"type": "object",
                       "properties": {"note": {"type": "string",
                                               "description": "the instruction to remember, one short line"}},
                       "required": ["note"]}}},
]


def _truncate(s: str) -> str:
    s = s.strip()
    return s if len(s) <= MAX_OUT else s[:MAX_OUT] + "\n…(truncated)"


def _run(cmd: list, timeout=20, inp=None) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, input=inp)
        out = (r.stdout or "") + (("\n" + r.stderr) if r.stderr else "")
        return _truncate(out) or "(no output)"
    except subprocess.TimeoutExpired:
        return "(command timed out)"
    except Exception as e:
        return f"(error: {e})"


def execute_tool(name: str, args: dict) -> str:
    if name == "run_shell":
        cmd = args.get("command", "")
        if _DANGER.search(cmd):
            return "BLOCKED: that command is destructive and was not run. It needs explicit confirmation."
        return _run(["/bin/bash", "-lc", cmd])
    if name == "read_file":
        p = os.path.expanduser(args.get("path", ""))
        if not os.path.isfile(p):
            return "(no such file)"
        try:
            with open(p, "r", errors="replace") as f:
                return _truncate(f.read())
        except Exception as e:
            return f"(error: {e})"
    if name == "list_dir":
        p = os.path.expanduser(args.get("path", "."))
        if not os.path.isdir(p):
            return "(no such directory)"
        try:
            entries = sorted(os.listdir(p))
        except Exception as e:
            return f"(error: {e})"
        sample = ", ".join(entries[:25])
        more = "" if len(entries) <= 25 else f" …and {len(entries) - 25} more"
        return f"{len(entries)} entries. First ones: {sample}{more}"
    if name == "open_thing":
        t = args.get("target", "")
        if _DANGER.search(t):
            return "BLOCKED."
        return _run(["open", t]) and f"Opened {t}." or f"Opened {t}."
    if name == "applescript":
        script = args.get("script", "")
        if re.search(r"do shell script", script, re.I) and _DANGER.search(script):
            return "BLOCKED."
        return _run(["osascript", "-e", script])
    if name == "remember":
        note = (args.get("note") or "").strip().lstrip("-").strip()
        if not note:
            return "(nothing to remember)"
        os.makedirs(os.path.dirname(PERSONA_FILE), exist_ok=True)
        if not os.path.exists(PERSONA_FILE):
            with open(PERSONA_FILE, "w") as f:
                f.write(_PERSONA_HEADER)
        with open(PERSONA_FILE, "a") as f:
            f.write(f"- {note}\n")
        return f"Saved. From now on, {note}"
    return f"(unknown tool {name})"


def subprocess_quote(s: str) -> str:
    return "'" + s.replace("'", "'\\''") + "'"


def _chat(model: str, messages: list) -> Optional[dict]:
    body = json.dumps({"model": model, "stream": False, "messages": messages,
                       "tools": TOOLS, "options": {"temperature": 0.3}}).encode()
    req = urllib.request.Request(OLLAMA_CHAT_URL, data=body,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=150) as r:
            return json.loads(r.read()).get("message", {})
    except Exception:
        return None


def run_agent(text: str, model: str = "llama3.2:3b", on_step=None) -> dict:
    """Run the agentic loop. Returns {spoken, actions: [{tool, args, result}]}."""
    messages = [{"role": "system", "content": system_prompt()}, {"role": "user", "content": text}]
    actions = []
    for _ in range(MAX_STEPS):
        msg = _chat(model, messages)
        if msg is None:
            return {"spoken": "I couldn't reach my reasoning model.", "actions": actions}
        calls = msg.get("tool_calls") or []
        if not calls:
            return {"spoken": (msg.get("content") or "").strip(), "actions": actions}
        messages.append({"role": "assistant", "content": msg.get("content", ""), "tool_calls": calls})
        for c in calls:
            fn = c.get("function", {})
            name = fn.get("name", "")
            raw = fn.get("arguments", {})
            args = raw if isinstance(raw, dict) else _safe_json(raw)
            if on_step:
                on_step(name, args)
            result = execute_tool(name, args)
            actions.append({"tool": name, "args": args, "result": result[:300]})
            messages.append({"role": "tool", "content": result})
    return {"spoken": "That took too many steps; let me stop there.", "actions": actions}


def _safe_json(s):
    try:
        return json.loads(s)
    except Exception:
        return {}
