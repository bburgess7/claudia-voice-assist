"""Runtime configuration for claudiad — persisted to ~/.claudia/config.json."""
from __future__ import annotations

import json
import os
import threading
from typing import Any, Dict

CONFIG_DIR = os.path.expanduser("~/.claudia")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")

DEFAULTS: Dict[str, Any] = {
    "engine": "kokoro",         # which TTS engine (see engines/registry)
    "voice": "af_heart",        # engine-specific voice id; None = engine default
    "rate": 1.0,                # speaking-rate multiplier, 0.5 (slow) .. 2.0 (fast)
    "verbosity": "summary",     # verbatim | summary | headline — how much to read
    "muted": False,             # global on/off for speaking
    "call_guard": True,         # auto-stay-silent while you're in a call (no surprise interruptions)
    "summarizer_model": "llama3.2:3b",  # local Ollama model for the spoken filter
    "agent_model": "qwen3-vl:30b",       # local Ollama tool-calling model for agentic /ask requests
    "wake_word": "hey claudia",
    "shared_secret": "",        # token for the quick-tunnel path (no SSO)
    "access_email": "",         # SSO: when set, remote requests authenticated by Cloudflare Access
                                # as this email are allowed (no secret needed). "super secure" path.
    "public_url": "",           # current tunnel URL (set by tunnel scripts) — used for QR pairing
    "sso": False,               # True when behind Cloudflare Access (QR omits the secret)
}

_lock = threading.Lock()
_state: Dict[str, Any] = {}


def load() -> Dict[str, Any]:
    global _state
    with _lock:
        data = dict(DEFAULTS)
        try:
            with open(CONFIG_PATH) as f:
                data.update(json.load(f))
        except (FileNotFoundError, json.JSONDecodeError):
            pass
        _state = data
        return dict(_state)


def get(key: str) -> Any:
    if not _state:
        load()
    return _state.get(key, DEFAULTS.get(key))


def update(patch: Dict[str, Any]) -> Dict[str, Any]:
    """Apply a partial update, persist, return the full config."""
    global _state
    with _lock:
        if not _state:
            _state.update(DEFAULTS)
        _state.update({k: v for k, v in patch.items() if k in DEFAULTS})
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(CONFIG_PATH, "w") as f:
            json.dump(_state, f, indent=2)
        return dict(_state)


def all() -> Dict[str, Any]:
    if not _state:
        load()
    return dict(_state)
