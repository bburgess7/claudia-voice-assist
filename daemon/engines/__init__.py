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
    names = ["macos_say"]
    for opt in ("kokoro", "kyutai"):
        try:
            __import__("daemon.engines." + opt, fromlist=[opt])
            names.append(opt)
        except Exception:
            pass
    return names
