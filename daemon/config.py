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
    "summarizer_model": "llama3.2:3b",  # local Ollama model for the spoken filter
    "wake_word": "hey claudia",
    "shared_secret": "",        # optional token required on remote WS connections
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
