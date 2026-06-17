#!/usr/bin/env python3
"""Claudia's ears — wake -> listen -> think -> reply, fully local. Optional sidecar (.venv-listen).

Two wake modes (CLAUDIA_WAKE_MODE):
  keyword  (default)  Custom phrase "hey claudia" with NO training: energy-VAD captures each
                      utterance, faster-whisper transcribes it, and if it starts with the wake
                      phrase we act. Bonus: a single-breath command ("Hey Claudia, what's the
                      status?") is handled in one turn — the words after the phrase ARE the command.
  oww                 openWakeWord pretrained model (e.g. hey_jarvis) — lowest CPU, fixed phrases.

Pipeline after wake: faster-whisper STT -> local Ollama brain (Claudia persona) -> daemon /say.
Nothing here imports into the daemon; it only calls the daemon's HTTP API to speak.

Run:  bash scripts/listen.sh        (needs mic permission for the terminal)
Env:  CLAUDIA_WAKE_MODE (keyword|oww), CLAUDIA_WAKE_PHRASE ("hey claudia"),
      CLAUDIA_WAKE (oww model, default hey_jarvis), CLAUDIA_BRAIN (Ollama model),
      CLAUDIA_STT (default base.en), CLAUDIA_URL
"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.request

import numpy as np
import sounddevice as sd

DAEMON = os.environ.get("CLAUDIA_URL", "http://127.0.0.1:4242")
WAKE_MODE = os.environ.get("CLAUDIA_WAKE_MODE", "keyword")
WAKE_PHRASE = os.environ.get("CLAUDIA_WAKE_PHRASE", "hey claudia").lower()
OWW_MODEL = os.environ.get("CLAUDIA_WAKE", "hey_jarvis")
BRAIN = os.environ.get("CLAUDIA_BRAIN", "llama3.2:3b")
STT_MODEL = os.environ.get("CLAUDIA_STT", "base.en")
OWW_THRESHOLD = float(os.environ.get("CLAUDIA_WAKE_THRESHOLD", "0.5"))

SR = 16000
FRAME = 1280              # 80ms @ 16kHz
SILENCE_RMS = 350         # int16 RMS below this counts as silence
SILENCE_HANG = 0.9        # trailing silence that ends a turn (s)
MAX_TURN = 9.0
# accept the wake phrase or close variants Whisper may emit ("hey, claudia", "hey cloudia", "claudia")
WAKE_RE = re.compile(r"^\W*(hey\W+)?cl?[ao]udi?a\b[\s,.:!?-]*", re.IGNORECASE)

PERSONA = (
    "You are Claudia, a warm, sharp, concise voice assistant running locally on Ben's Mac. You are "
    "spoken aloud, so reply in 1-3 short sentences of plain conversational English. No markdown, no "
    "lists, no code, no symbols. If asked to do something you can't do from here, say so briefly. "
    "Be helpful and a little witty, never verbose."
)


def cue():
    subprocess.run(["afplay", "/System/Library/Sounds/Tink.aiff"], stderr=subprocess.DEVNULL)


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


def respond(text):
    """Send a command transcript to the brain and speak the reply."""
    if not text or muted():
        return
    print(f"[you] {text}", flush=True)
    reply = ask_brain(text)
    if reply:
        print(f"[claudia] {reply}", flush=True)
        daemon("/say", {"text": reply})
    time.sleep(0.4)


class Mic:
    def __init__(self):
        self.stream = sd.InputStream(samplerate=SR, channels=1, dtype="int16", blocksize=FRAME)
        self.stream.start()

    def frame(self):
        data, _ = self.stream.read(FRAME)
        return data[:, 0]

    def capture_utterance(self, first=None):
        """Record from now until trailing silence; return float32 audio."""
        buf = [first] if first is not None else [self.frame()]
        t0 = last_voice = time.time()
        while True:
            f = self.frame()
            buf.append(f)
            if float(np.sqrt(np.mean(f.astype(np.float32) ** 2))) > SILENCE_RMS:
                last_voice = time.time()
            if time.time() - last_voice > SILENCE_HANG or time.time() - t0 > MAX_TURN:
                break
        return np.concatenate(buf).astype(np.float32) / 32768.0


def transcribe(stt, audio):
    segments, _ = stt.transcribe(audio, language="en", vad_filter=True)
    return " ".join(s.text for s in segments).strip()


def run_keyword(mic, stt):
    print(f"[listen] keyword mode — say '{WAKE_PHRASE}'.", flush=True)
    while True:
        f = mic.frame()
        if float(np.sqrt(np.mean(f.astype(np.float32) ** 2))) <= SILENCE_RMS:
            continue
        audio = mic.capture_utterance(first=f)        # grab the whole spoken phrase
        text = transcribe(stt, audio)
        if not text:
            continue
        m = WAKE_RE.match(text)
        if not m:
            continue
        daemon("/stop")                                # barge-in
        command = text[m.end():].strip()
        if command:                                    # single-breath: "Hey Claudia, do X"
            respond(command)
        else:                                          # just the wake word -> capture the command
            cue()
            respond(transcribe(stt, mic.capture_utterance()))


def run_oww(mic, stt):
    from openwakeword.model import Model
    import openwakeword
    try:
        openwakeword.utils.download_models()
    except Exception:
        pass
    oww = Model(wakeword_models=[OWW_MODEL], inference_framework="onnx")
    print(f"[listen] openWakeWord mode — say '{OWW_MODEL.replace('_', ' ')}'.", flush=True)
    while True:
        if oww.predict(mic.frame()).get(OWW_MODEL, 0.0) < OWW_THRESHOLD:
            continue
        oww.reset()
        daemon("/stop")
        cue()
        respond(transcribe(stt, mic.capture_utterance()))
        oww.reset()


def main():
    print(f"[listen] loading STT '{STT_MODEL}' ...", flush=True)
    from faster_whisper import WhisperModel
    stt = WhisperModel(STT_MODEL, device="cpu", compute_type="int8")
    mic = Mic()
    (run_oww if WAKE_MODE == "oww" else run_keyword)(mic, stt)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
