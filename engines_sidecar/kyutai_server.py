#!/usr/bin/env python3
"""Kyutai TTS sidecar — runs in its OWN venv (.venv-kyutai, moshi-mlx). Lowest-latency conversational
voice. Isolated from the daemon (and from Kokoro) so its mlx pin can't break anything else.

Loads the Kyutai 1.6B model once (8-bit quantized) and keeps it warm. Mirrors moshi_mlx.run_tts's
model-loading + generation flow, exposed over a tiny stdlib HTTP API:

  POST /tts    {text, voice, speed} -> audio/wav bytes
  GET  /voices -> {"voices": [...]}
  GET  /health -> {"ok": true, "loading": bool}

Env: CLAUDIA_KYUTAI_PORT (default 4244), CLAUDIA_KYUTAI_QUANTIZE (default 8).
Note: Kyutai's pace is implicit; `speed` is accepted but not applied (rate control is best via Kokoro).
"""
import io
import json
import os
import threading
import time
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np
import mlx.core as mx
import mlx.nn as nn
import sentencepiece

from moshi_mlx import models
from moshi_mlx.utils.loaders import hf_get
from moshi_mlx.models.tts import TTSModel, DEFAULT_DSM_TTS_REPO, DEFAULT_DSM_TTS_VOICE_REPO

PORT = int(os.environ.get("CLAUDIA_KYUTAI_PORT", "4244"))
QUANTIZE = int(os.environ.get("CLAUDIA_KYUTAI_QUANTIZE", "8"))

VOICES = [
    {"id": "alba-mackenna/casual.wav", "label": "Alba — casual ★"},
    {"id": "alba-mackenna/announcer.wav", "label": "Alba — announcer"},
    {"id": "alba-mackenna/merchant.wav", "label": "Alba — merchant"},
    {"id": "alba-mackenna/a-moment-by.wav", "label": "Alba — narration"},
]

_state = {"loading": True}
_lock = threading.Lock()
_tts = None
_cfg = {}


def _load():
    global _tts, _cfg
    repo = DEFAULT_DSM_TTS_REPO
    raw = json.load(open(hf_get("config.json", repo)))
    mimi_w = hf_get(raw["mimi_name"], repo)
    moshi_w = hf_get(raw.get("moshi_name", "model.safetensors"), repo)
    tok = hf_get(hf_get(raw["tokenizer_name"], repo))

    lm_config = models.LmConfig.from_config_dict(raw)
    model = models.Lm(lm_config)
    model.set_dtype(mx.bfloat16)
    model.load_pytorch_weights(str(moshi_w), lm_config, strict=True)
    if QUANTIZE:
        nn.quantize(model.depformer, bits=QUANTIZE)
        for layer in model.transformer.layers:
            nn.quantize(layer.self_attn, bits=QUANTIZE)
            nn.quantize(layer.gating, bits=QUANTIZE)

    text_tok = sentencepiece.SentencePieceProcessor(str(tok))
    audio_tok = models.mimi.Mimi(models.mimi_202407(lm_config.generated_codebooks))
    audio_tok.load_pytorch_weights(str(mimi_w), strict=True)

    tts = TTSModel(model, audio_tok, text_tok, voice_repo=DEFAULT_DSM_TTS_VOICE_REPO,
                   n_q=32, temp=0.6, cfg_coef=2.0, max_padding=8, initial_padding=2,
                   final_padding=4, padding_bonus=0.0, raw_config=raw)
    cfg = {"no_text": True, "no_prefix": True, "cond": None}
    if tts.valid_cfg_conditionings:
        cfg["cond"] = tts.cfg_coef
        tts.cfg_coef = 1.0
        cfg["no_text"] = cfg["no_prefix"] = False
    _tts, _cfg = tts, cfg
    _state["loading"] = False
    print("[kyutai] ready on :%d" % PORT, flush=True)


def _synth(text, voice):
    with _lock:
        tts, mimi = _tts, _tts.mimi
        entries = tts.prepare_script([text], padding_between=1)
        if tts.multi_speaker:
            attrs = tts.make_condition_attributes([tts.get_voice_path(voice)], _cfg["cond"])
            prefixes = None
        else:
            attrs = tts.make_condition_attributes([], _cfg["cond"])
            prefixes = [tts.get_prefix(hf_get(voice, DEFAULT_DSM_TTS_VOICE_REPO,
                                              check_local_file_exists=True))]
        result = tts.generate([entries], [attrs], prefixes=prefixes,
                              cfg_is_no_prefix=_cfg["no_prefix"], cfg_is_no_text=_cfg["no_text"])
        wavs = mx.concat([mimi.decode_step(f) for f in result.frames], axis=-1)
        end = result.end_steps[0]
        n = wavs.shape[-1] if end is None else int(mimi.sample_rate * (end + tts.final_padding) / mimi.frame_rate)
        wav = wavs[0, :, :n]
        if prefixes is not None:
            start = int(mimi.sample_rate * prefixes[0].shape[-1] / mimi.frame_rate)
            wav = wav[:, start:]
        return np.array(mx.clip(wav, -1, 1)).reshape(-1), mimi.sample_rate


def _speak_stream(text, voice):
    """STREAMING: decode + play each frame as it's generated (low time-to-first-audio). Returns the
    measured time-to-first-audio in seconds."""
    import sounddevice as sd
    with _lock:
        tts, mimi = _tts, _tts.mimi
        entries = tts.prepare_script([text], padding_between=1)
        if tts.multi_speaker:
            attrs = tts.make_condition_attributes([tts.get_voice_path(voice)], _cfg["cond"])
            prefixes = None
        else:
            attrs = tts.make_condition_attributes([], _cfg["cond"])
            prefixes = [tts.get_prefix(hf_get(voice, DEFAULT_DSM_TTS_VOICE_REPO,
                                              check_local_file_exists=True))]
        # frames covered by the voice-prefix must be skipped (they're the conditioning audio)
        skip = 0
        if prefixes is not None:
            skip = int(prefixes[0].shape[-1])
        out = sd.OutputStream(samplerate=mimi.sample_rate, channels=1, dtype="float32",
                              blocksize=1920)
        out.start()
        state = {"seen": 0, "t0": None, "tfa": None}

        def on_frame(frame):
            f = mx.array(frame)[:, :, None]   # match the shape decode_step expects (see TTSModel.generate)
            i = state["seen"]; state["seen"] += 1
            if i < skip:
                _ = mimi.decode_step(f)       # keep decoder state in sync, don't play prefix
                return
            pcm = np.array(mx.clip(mimi.decode_step(f), -1, 1)).reshape(-1).astype("float32")
            if state["t0"] is None:
                state["t0"] = time.time()
                state["tfa"] = state["t0"] - state["start"]
            out.write(pcm)

        state["start"] = time.time()
        tts.generate([entries], [attrs], prefixes=prefixes,
                     cfg_is_no_prefix=_cfg["no_prefix"], cfg_is_no_text=_cfg["no_text"],
                     on_frame=on_frame)
        out.stop(); out.close()
        return state["tfa"] or 0.0


def _wav_bytes(samples, sr):
    pcm = (np.clip(samples, -1, 1) * 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr); w.writeframes(pcm.tobytes())
    return buf.getvalue()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            return self._json(200, {"ok": not _state["loading"], "loading": _state["loading"]})
        if self.path == "/voices":
            return self._json(200, {"voices": VOICES})
        self._json(404, {"error": "not found"})

    def do_POST(self):
        if self.path not in ("/tts", "/speak"):
            return self._json(404, {"error": "not found"})
        if _state["loading"]:
            return self._json(503, {"error": "model loading"})
        n = int(self.headers.get("Content-Length", 0))
        try:
            req = json.loads(self.rfile.read(n) or b"{}")
            text = (req.get("text") or "").strip()
            voice = req.get("voice") or VOICES[0]["id"]
            if self.path == "/speak":
                # STREAMING local playback — lowest time-to-first-audio
                tfa = _speak_stream(text, voice)
                return self._json(200, {"ok": True, "time_to_first_audio": round(tfa, 3)})
            samples, sr = _synth(text, voice)            # /tts -> full WAV (for remote/WS)
            wav = _wav_bytes(samples, sr)
            self.send_response(200); self.send_header("Content-Type", "audio/wav")
            self.send_header("Content-Length", str(len(wav))); self.end_headers(); self.wfile.write(wav)
        except Exception as e:
            self._json(500, {"error": str(e)})


if __name__ == "__main__":
    print("[kyutai] loading model (this takes a bit on first run)...", flush=True)
    threading.Thread(target=_load, daemon=True).start()
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
