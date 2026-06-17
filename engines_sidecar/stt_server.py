#!/usr/bin/env python3
"""Local speech-to-text sidecar (faster-whisper) — runs in .venv-listen. Private, on-device STT so
"tap to talk" works without sending audio to Google. Loads the model once, kept warm.

  POST /stt   (raw audio bytes: webm/opus, mp4, wav…) -> {"text": "..."}
  GET  /health -> {"ok": true, "loading": bool}

Env: CLAUDIA_STT_PORT (default 4245), CLAUDIA_STT (model, default base.en).
"""
import json
import os
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("CLAUDIA_STT_PORT", "4245"))
MODEL = os.environ.get("CLAUDIA_STT", "base.en")

_state = {"loading": True}
_stt = None


def _load():
    global _stt
    from faster_whisper import WhisperModel
    _stt = WhisperModel(MODEL, device="cpu", compute_type="int8")
    _state["loading"] = False
    print(f"[stt] ready on :{PORT} (model {MODEL})", flush=True)


def _transcribe(audio: bytes) -> str:
    fd, path = tempfile.mkstemp(suffix=".bin")
    os.write(fd, audio)
    os.close(fd)
    try:
        segments, _ = _stt.transcribe(path, language="en", vad_filter=True)
        return " ".join(s.text for s in segments).strip()
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            return self._json(200, {"ok": not _state["loading"], "loading": _state["loading"]})
        self._json(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/stt":
            return self._json(404, {"error": "not found"})
        if _state["loading"]:
            return self._json(503, {"error": "loading"})
        n = int(self.headers.get("Content-Length", 0))
        try:
            text = _transcribe(self.rfile.read(n))
            self._json(200, {"text": text})
        except Exception as e:
            self._json(500, {"error": str(e)})


if __name__ == "__main__":
    print("[stt] loading model…", flush=True)
    threading.Thread(target=_load, daemon=True).start()
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
