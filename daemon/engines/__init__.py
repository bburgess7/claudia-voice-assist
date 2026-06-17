"""Engine registry. Add a neural engine here once its module exists."""
from __future__ import annotations

from typing import Dict
from .base import TTSEngine
from .macos_say import MacOSSayEngine

_ENGINES: Dict[str, TTSEngine] = {}


def get_engine(name: str) -> TTSEngine:
    if name not in _ENGINES:
        try:
            if name == "macos_say":
                _ENGINES[name] = MacOSSayEngine()
            elif name == "kokoro":
                from .kokoro import KokoroEngine
                _ENGINES[name] = KokoroEngine()
            elif name == "kyutai":
                from .kyutai import KyutaiEngine
                _ENGINES[name] = KyutaiEngine()
            else:
                return get_engine("macos_say")
        except Exception:
            # Any engine that fails to import/init falls back to the always-available starter.
            return get_engine("macos_say")
    return _ENGINES[name]


def available() -> list:
    """macos_say is always available; neural engines are listed only if their sidecar answers."""
    import os
    import urllib.request
    names = ["macos_say"]
    sidecars = {
        "kokoro": os.environ.get("CLAUDIA_KOKORO_URL", "http://127.0.0.1:4243"),
        "kyutai": os.environ.get("CLAUDIA_KYUTAI_URL", "http://127.0.0.1:4244"),
    }
    for name, url in sidecars.items():
        try:
            with urllib.request.urlopen(url + "/health", timeout=0.6) as r:
                if r.status == 200:
                    names.append(name)
        except Exception:
            pass
    return names
