"""Serialized speech manager: one queue, one worker, so Claudia never talks over herself.

Each utterance is summarized (per verbosity) then spoken locally. If remote clients are
connected, a WAV of the same utterance is fanned out to them. `interrupt()` clears the queue
and stops in-progress playback (used by the wake word / push-to-talk barge-in).
"""
from __future__ import annotations

import queue
import threading
from dataclasses import dataclass
from typing import Callable, List, Optional

from . import config
from . import summarizer
from .engines import get_engine


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
        self.has_remote: Callable[[], bool] = lambda: False

    def enqueue(self, text: str, mode: Optional[str] = None) -> str:
        """Summarize `text` per mode/verbosity and queue it. Returns the spoken text."""
        cfg = config.all()
        if cfg.get("muted"):
            return ""
        mode = mode or cfg.get("verbosity", "summary")
        spoken = summarizer.to_speech(text, mode=mode, model=cfg.get("summarizer_model"))
        if not spoken.strip():
            return ""
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
