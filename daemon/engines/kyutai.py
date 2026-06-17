"""Kyutai engine — thin HTTP client to the Kyutai sidecar (engines_sidecar/kyutai_server.py).

Lowest-latency conversational voice. Like the Kokoro engine, the daemon imports no ML here — it just
asks the sidecar (its own isolated venv) for WAV bytes. Start the sidecar with scripts/kyutai.sh.
"""
from __future__ import annotations

import json
import os
import urllib.request
from typing import List, Dict, Optional

from .base import TTSEngine
from . import player

SIDECAR = os.environ.get("CLAUDIA_KYUTAI_URL", "http://127.0.0.1:4244")


class KyutaiEngine(TTSEngine):
    name = "kyutai"

    def _synth(self, text: str, voice: Optional[str], rate: float) -> bytes:
        body = json.dumps({"text": text, "voice": voice, "speed": rate}).encode()
        req = urllib.request.Request(SIDECAR + "/tts", data=body,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.read()

    def speak_local(self, text: str, voice: Optional[str] = None, rate: float = 1.0) -> None:
        # STREAMING path: the sidecar generates + plays frame-by-frame (low time-to-first-audio).
        try:
            body = json.dumps({"text": text, "voice": voice}).encode()
            req = urllib.request.Request(SIDECAR + "/speak", data=body,
                                         headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=120).read()
        except Exception:
            player.play_wav_bytes(self._synth(text, voice, rate))   # fallback: batch + afplay

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
