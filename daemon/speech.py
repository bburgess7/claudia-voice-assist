"""Serialized speech manager: one queue, one worker, so Claudia never talks over herself.

Each utterance is summarized (per verbosity) then spoken locally. If remote clients are
connected, a WAV of the same utterance is fanned out to them. `interrupt()` clears the queue
and stops in-progress playback (used by the wake word / push-to-talk barge-in).
"""
from __future__ import annotations

import queue
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Callable, List, Optional

from . import config
from . import summarizer
from .engines import get_engine

# Processes that exist only DURING an active call/meeting (permission-free signal — no Accessibility).
#   CptHost = Zoom while in a meeting.  Add others as needed.
_CALL_PROCS = ["CptHost"]
_call_cache = {"t": 0.0, "v": False}


def in_call() -> bool:
    """Best-effort 'are you on a call right now' check, cached ~2s. Conservative: only true when a
    known in-meeting process is running. The manual mute is the guaranteed control."""
    now = time.time()
    if now - _call_cache["t"] < 2.0:
        return _call_cache["v"]
    v = False
    try:
        for p in _CALL_PROCS:
            if subprocess.run(["pgrep", "-x", p], capture_output=True).returncode == 0:
                v = True
                break
    except Exception:
        pass
    _call_cache.update(t=now, v=v)
    return v


@dataclass
class Utterance:
    text: str            # already speech-ready
    raw: str             # original, for transcript
    rate: float
    voice: Optional[str]


class SpeechManager:
    def __init__(self) -> None:
        self._q: "queue.Queue[Optional[Utterance]]" = queue.Queue()
        self._worker = threading.Thread(target=self._run, daemon=True)
        self._worker.start()
        self.speaking = False
        # callbacks the server registers: (wav_bytes, utterance) for remote fan-out, and transcript
        self.on_audio: Optional[Callable[[bytes, Utterance], None]] = None
        self.on_transcript: Optional[Callable[[str, str], None]] = None  # (raw, spoken)
        self.on_idle: Optional[Callable[[], None]] = None
        self.has_remote: Callable[[], bool] = lambda: False

    def enqueue(self, text: str, mode: Optional[str] = None, prefix: Optional[str] = None) -> str:
        """Summarize `text` per mode/verbosity and queue it. `prefix` (e.g. a project name) is spoken
        first, unsummarized, so context like which project survives. Returns the spoken text."""
        cfg = config.all()
        if cfg.get("muted"):
            return ""
        mode = mode or cfg.get("verbosity", "summary")
        spoken = summarizer.to_speech(text, mode=mode, model=cfg.get("summarizer_model"))
        if not spoken.strip():
            return ""
        if prefix and prefix.strip():
            spoken = f"{prefix.strip()}. {spoken}"
        self._q.put(Utterance(text=spoken, raw=text, rate=float(cfg.get("rate", 1.0)),
                              voice=cfg.get("voice")))
        return spoken

    def interrupt(self) -> None:
        try:
            while True:
                self._q.get_nowait()
        except queue.Empty:
            pass
        get_engine(config.get("engine")).stop()

    def _run(self) -> None:
        while True:
            item = self._q.get()
            if item is None:
                continue
            # No surprises: stay silent while you're on a call (manual mute always wins too).
            if config.get("call_guard") and in_call():
                if self.on_idle:
                    self.on_idle()
                continue
            engine = get_engine(config.get("engine"))
            self.speaking = True
            try:
                if self.on_transcript:
                    self.on_transcript(item.raw, item.text)
                if self.on_audio and self.has_remote():
                    try:
                        wav = engine.synthesize_wav(item.text, item.voice, item.rate)
                        self.on_audio(wav, item)
                    except Exception:
                        pass
                engine.speak_local(item.text, item.voice, item.rate)
            except Exception:
                pass
            finally:
                self.speaking = False
                if self._q.empty() and self.on_idle:
                    self.on_idle()
