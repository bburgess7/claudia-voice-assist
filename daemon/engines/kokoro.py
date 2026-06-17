"""Kokoro engine — thin HTTP client to the kokoro-onnx sidecar (engines_sidecar/kokoro_server.py).

The daemon never imports any ML library; it just asks the sidecar for WAV bytes. This is what keeps
the daemon lean and unbreakable regardless of the audio stack's dependency churn.
"""
from __future__ import annotations

import json
import os
import urllib.request
from typing import List, Dict, Optional

from .base import TTSEngine
from . import player

SIDECAR = os.environ.get("CLAUDIA_KOKORO_URL", "http://127.0.0.1:4243")


class KokoroEngine(TTSEngine):
    name = "kokoro"

    def _synth(self, text: str, voice: Optional[str], rate: float) -> bytes:
        body = json.dumps({"text": text, "voice": voice or "af_heart", "speed": rate}).encode()
        req = urllib.request.Request(SIDECAR + "/tts", data=body,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.read()

    def speak_local(self, text: str, voice: Optional[str] = None, rate: float = 1.0) -> None:
        player.play_wav_bytes(self._synth(text, voice, rate))

    def synthesize_wav(self, text: str, voice: Optional[str] = None, rate: float = 1.0) -> bytes:
        return self._synth(text, voice, rate)

    def stop(self) -> None:
        player.stop()

    def list_voices(self) -> List[Dict[str, str]]:
        try:
            with urllib.request.urlopen(SIDECAR + "/voices", timeout=5) as r:
                return json.loads(r.read()).get("voices", [])
        except Exception:
            return []
