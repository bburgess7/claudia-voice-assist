"""Starter engine: macOS built-in `say`. Zero install, always available, proves the pipeline.

Swap this for a neural engine (Kokoro / Sesame CSM / Kyutai) by adding a sibling module that
implements the same TTSEngine interface and registering it. Nothing else has to change.
"""
from __future__ import annotations

import os
import re
import shutil
import signal
import subprocess
import tempfile
from typing import List, Dict, Optional

from .base import TTSEngine

BASE_WPM = 175  # `say` default-ish; rate multiplier scales this


class MacOSSayEngine(TTSEngine):
    name = "macos_say"

    def __init__(self) -> None:
        self._proc: Optional[subprocess.Popen] = None

    def _wpm(self, rate: float) -> str:
        wpm = int(max(0.5, min(2.5, rate)) * BASE_WPM)
        return str(wpm)

    def speak_local(self, text: str, voice: Optional[str] = None, rate: float = 1.0) -> None:
        self.stop()
        cmd = ["say", "-r", self._wpm(rate)]
        if voice:
            cmd += ["-v", voice]
        cmd.append(text)
        self._proc = subprocess.Popen(cmd)
        self._proc.wait()
        self._proc = None

    def synthesize_wav(self, text: str, voice: Optional[str] = None, rate: float = 1.0) -> bytes:
        fd, path = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        try:
            cmd = ["say", "-r", self._wpm(rate), "-o", path,
                   "--file-format=WAVE", "--data-format=LEI16@22050"]
            if voice:
                cmd += ["-v", voice]
            cmd.append(text)
            subprocess.run(cmd, check=True)
            with open(path, "rb") as f:
                return f.read()
        finally:
            try:
                os.remove(path)
            except OSError:
                pass

    def stop(self) -> None:
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.send_signal(signal.SIGTERM)
            except ProcessLookupError:
                pass
        self._proc = None

    def list_voices(self) -> List[Dict[str, str]]:
        if not shutil.which("say"):
            return []
        out = subprocess.run(["say", "-v", "?"], capture_output=True, text=True).stdout
        voices: List[Dict[str, str]] = []
        for line in out.splitlines():
            m = re.match(r"^(.+?)\s+([a-z]{2}_[A-Z]{2})\s+#\s*(.*)$", line)
            if not m:
                continue
            name, locale, sample = m.group(1).strip(), m.group(2), m.group(3)
            if not locale.startswith("en"):
                continue
            nice = any(tag in name for tag in ("Premium", "Enhanced"))
            voices.append({"id": name, "label": name + (" ★" if nice else ""), "locale": locale})
        # nicer (Premium/Enhanced) voices first
        voices.sort(key=lambda v: ("★" not in v["label"], v["id"]))
        return voices
