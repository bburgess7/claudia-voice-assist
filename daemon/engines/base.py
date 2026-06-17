"""Pluggable TTS engine interface.

Every engine implements three things:
  - speak_local(text, voice, rate): play audio on THIS machine's speakers (low-latency path)
  - synthesize_wav(text, voice, rate) -> bytes: produce a WAV for remote/mobile clients
  - list_voices() -> list of {id, label}

`rate` is a multiplier where 1.0 == the engine's natural pace. Engines map it to their own units.
Keeping the interface this small is what makes the whole stack portable and swappable.
"""
from __future__ import annotations

from typing import List, Dict, Optional


class TTSEngine:
    name: str = "base"

    def speak_local(self, text: str, voice: Optional[str] = None, rate: float = 1.0) -> None:
        raise NotImplementedError

    def synthesize_wav(self, text: str, voice: Optional[str] = None, rate: float = 1.0) -> bytes:
        raise NotImplementedError

    def list_voices(self) -> List[Dict[str, str]]:
        return []

    def stop(self) -> None:
        """Interrupt any in-progress local playback. Optional."""
        return None
