#!/usr/bin/env python3
"""Claudia's ears — wake-word -> listen -> think -> reply, fully local.

Optional sidecar (its own venv .venv-listen). Pipeline:
    openWakeWord ("hey jarvis" by default)  ->  energy-VAD capture  ->  faster-whisper STT
    ->  local LLM brain (Ollama, Claudia persona)  ->  daemon /say  ->  Claudia speaks.

Nothing here imports into the daemon; it only calls the daemon's HTTP API to speak. So even if the
audio stack misbehaves, the core voice/daemon is untouched.

Run:  ./.venv-listen/bin/python listen/listen.py
Env:  CLAUDIA_WAKE (default hey_jarvis), CLAUDIA_BRAIN (Ollama model, default llama3.2:3b),
      CLAUDIA_STT (default base.en), CLAUDIA_URL (default http://127.0.0.1:4242)
"""
import json
import os
import subprocess
import sys
import time
import urllib.request

import numpy as np
import sounddevice as sd

DAEMON = os.environ.get("CLAUDIA_URL", "http://127.0.0.1:4242")
WAKE = os.environ.get("CLAUDIA_WAKE", "hey_jarvis")     # pretrained openWakeWord model
BRAIN = os.environ.get("CLAUDIA_BRAIN", "llama3.2:3b")  # local Ollama chat model
STT_MODEL = os.environ.get("CLAUDIA_STT", "base.en")
WAKE_THRESHOLD = float(os.environ.get("CLAUDIA_WAKE_THRESHOLD", "0.5"))

SR = 16000
FRAME = 1280              # 80ms @ 16kHz — openWakeWord's expected chunk
SILENCE_RMS = 350         # int16 RMS below this counts as silence
SILENCE_HANG = 0.9        # seconds of trailing silence that ends a turn
MAX_TURN = 9.0            # hard cap on a single utterance

PERSONA = (
    "You are Claudia, a warm, sharp, concise voice assistant running locally on Ben's Mac. You are "
    "spoken aloud, so reply in 1-3 short sentences of plain conversational English. No markdown, no "
    "lists, no code, no symbols. If asked to do something you can't do from here, say so briefly. "
    "Be helpful and a little witty, never verbose."
)


def cue():
    # non-verbal "I'm listening" so we don't talk over the user
    subprocess.run(["afplay", "/System/Library/Sounds/Tink.aiff"],
                   stderr=subprocess.DEVNULL)


def daemon(path, payload=None, method="POST"):
    data = json.dumps(payload).encode() if payload is not None else None
    try:
        req = urllib.request.Request(DAEMON + path, data=data, method=method,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except Exception:
        return {}


def muted():
    return bool(daemon("/config", method="GET").get("muted"))


def ask_brain(text):
    body = json.dumps({
        "model": BRAIN, "stream": False,
        "messages": [{"role": "system", "content": PERSONA}, {"role": "user", "content": text}],
        "options": {"temperature": 0.6, "num_predict": 160},
    }).encode()
    try:
        req = urllib.request.Request("http://127.0.0.1:11434/api/chat", data=body,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=40) as r:
            return json.loads(r.read()).get("message", {}).get("content", "").strip()
    except Exception:
        return ""


def main():
    from openwakeword.model import Model
    import openwakeword

    try:
        openwakeword.utils.download_models()
    except Exception:
        pass
    print(f"[listen] loading wake model '{WAKE}' + STT '{STT_MODEL}' ...", flush=True)
    oww = Model(wakeword_models=[WAKE], inference_framework="onnx")

    from faster_whisper import WhisperModel
    stt = WhisperModel(STT_MODEL, device="cpu", compute_type="int8")
    print(f"[listen] ready. Say '{WAKE.replace('_', ' ')}'.", flush=True)

    stream = sd.InputStream(samplerate=SR, channels=1, dtype="int16", blocksize=FRAME)
    stream.start()

    def read_frame():
        data, _ = stream.read(FRAME)
        return data[:, 0]

    while True:
        frame = read_frame()
        scores = oww.predict(frame)
        if scores.get(WAKE, 0.0) < WAKE_THRESHOLD:
            continue

        # --- wake! barge-in any current speech, acknowledge, capture the turn ---
        oww.reset()
        daemon("/stop")
        cue()
        buf = [read_frame()]
        t0 = time.time()
        last_voice = time.time()
        while True:
            f = read_frame()
            buf.append(f)
            rms = float(np.sqrt(np.mean(f.astype(np.float32) ** 2)))
            now = time.time()
            if rms > SILENCE_RMS:
                last_voice = now
            if now - last_voice > SILENCE_HANG or now - t0 > MAX_TURN:
                break

        audio = np.concatenate(buf).astype(np.float32) / 32768.0
        segments, _ = stt.transcribe(audio, language="en", vad_filter=True)
        text = " ".join(s.text for s in segments).strip()
        if not text:
            continue
        print(f"[you] {text}", flush=True)

        if muted():
            continue
        reply = ask_brain(text)
        if reply:
            print(f"[claudia] {reply}", flush=True)
            daemon("/say", {"text": reply})       # verbatim — brain already wrote spoken prose
        # give playback a beat before re-arming the wake word (avoid self-trigger)
        time.sleep(0.4)
        oww.reset()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
