"""Shared local audio playback via macOS `afplay`, with stop support for barge-in."""
from __future__ import annotations

import os
import signal
import subprocess
import tempfile
from typing import Optional

_proc: Optional[subprocess.Popen] = None


def play_wav_bytes(wav: bytes) -> None:
    global _proc
    stop()
    fd, path = tempfile.mkstemp(suffix=".wav")
    os.write(fd, wav)
    os.close(fd)
    try:
        _proc = subprocess.Popen(["afplay", path])
        _proc.wait()
    finally:
        _proc = None
        try:
            os.remove(path)
        except OSError:
            pass


def stop() -> None:
    global _proc
    if _proc and _proc.poll() is None:
        try:
            _proc.send_signal(signal.SIGTERM)
        except ProcessLookupError:
            pass
    _proc = None
