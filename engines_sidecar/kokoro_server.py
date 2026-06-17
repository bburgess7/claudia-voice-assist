#!/usr/bin/env python3
"""Kokoro TTS sidecar — runs in its OWN venv (.venv-kokoro, kokoro-onnx).

Isolated from the daemon so its ML deps can never destabilize claudiad. Loads the model once and
keeps it warm. Stdlib-only HTTP so this venv needs nothing but kokoro-onnx + soundfile.

  POST /tts    {text, voice, speed} -> audio/wav bytes
  GET  /voices -> {"voices": [...]}
  GET  /health -> {"ok": true}

Env: CLAUDIA_KOKORO_PORT (default 4243), CLAUDIA_KOKORO_DIR (dir holding the .onnx + .bin).
"""
import io
import json
import os
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np
import soundfile as sf
from kokoro_onnx import Kokoro

PORT = int(os.environ.get("CLAUDIA_KOKORO_PORT", "4243"))
MODEL_DIR = os.environ.get(
    "CLAUDIA_KOKORO_DIR", os.path.join(os.path.dirname(os.path.dirname(__file__)), ".venv-kokoro"))

# Curated, natural-first subset (the full set is ~54 voices).
VOICES = [
    {"id": "af_heart", "label": "Heart (warm, female) ★"},
    {"id": "af_bella", "label": "Bella (female)"},
    {"id": "af_nicole", "label": "Nicole (soft, female)"},
    {"id": "af_sky", "label": "Sky (female)"},
    {"id": "am_michael", "label": "Michael (male)"},
    {"id": "am_fenrir", "label": "Fenrir (deep, male)"},
    {"id": "am_onyx", "label": "Onyx (male)"},
    {"id": "bf_emma", "label": "Emma (British, female)"},
    {"id": "bm_george", "label": "George (British, male)"},
]

print("[kokoro] loading model...", flush=True)
_kokoro = Kokoro(os.path.join(MODEL_DIR, "kokoro-v1.0.onnx"),
                 os.path.join(MODEL_DIR, "voices-v1.0.bin"))
print("[kokoro] ready on :%d" % PORT, flush=True)


def _wav_bytes(samples, sr) -> bytes:
    samples = np.asarray(samples, dtype=np.float32)
    pcm = np.clip(samples, -1.0, 1.0)
    pcm = (pcm * 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())
    return buf.getvalue()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass  # quiet

    def _json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            return self._json(200, {"ok": True})
        if self.path == "/voices":
            return self._json(200, {"voices": VOICES})
        self._json(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/tts":
            return self._json(404, {"error": "not found"})
        n = int(self.headers.get("Content-Length", 0))
        try:
            req = json.loads(self.rfile.read(n) or b"{}")
            text = (req.get("text") or "").strip()
            voice = req.get("voice") or "af_heart"
            speed = float(req.get("speed", 1.0))
            speed = max(0.5, min(2.0, speed))
            samples, sr = _kokoro.create(text, voice=voice, speed=speed, lang="en-us")
            wav = _wav_bytes(samples, sr)
            self.send_response(200)
            self.send_header("Content-Type", "audio/wav")
            self.send_header("Content-Length", str(len(wav)))
            self.end_headers()
            self.wfile.write(wav)
        except Exception as e:
            self._json(500, {"error": str(e)})


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
