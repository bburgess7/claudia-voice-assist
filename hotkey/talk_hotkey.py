#!/usr/bin/env python3
"""Global push-to-talk hotkey for Claudia. Works in ANY app.

  HOLD the hotkey  -> records while held, RELEASE sends it (push-to-talk).
  DOUBLE-TAP it    -> toggles hands-free CONVERSATION mode (she listens, you talk, she replies,
                      and it keeps going turn after turn until you double-tap again).

Audio is captured locally and sent to the daemon's /talk (local Whisper -> agent -> speaks). Nothing
leaves your Mac. Default hotkey: RIGHT OPTION (⌥). Change with CLAUDIA_HOTKEY (a pynput key name).

Requires Accessibility permission for the terminal/app that launches it
(System Settings → Privacy & Security → Accessibility). Run: bash scripts/setup-hotkey.sh
"""
import io
import os
import subprocess
import sys
import threading
import time
import urllib.request
import wave

import numpy as np
import sounddevice as sd
from pynput import keyboard

DAEMON = os.environ.get("CLAUDIA_URL", "http://127.0.0.1:4242")
# Right Command by default: it's on the MacBook keyboard and (unlike Right Option) doesn't type
# accented characters when held alone. Override with CLAUDIA_HOTKEY (any pynput Key name, e.g. alt_r).
HOTKEY_NAME = os.environ.get("CLAUDIA_HOTKEY", "cmd_r")
HOLD_THRESHOLD = 0.35      # held longer than this = push-to-talk; shorter = a tap
DOUBLE_TAP = 0.40          # two taps within this window = toggle conversation
SR = 16000
SILENCE_RMS = 350
SILENCE_HANG = 0.9
MAX_TURN = 12.0

HOTKEY = getattr(keyboard.Key, HOTKEY_NAME, keyboard.Key.alt_r)


def cue(sound="Tink"):
    subprocess.run(["afplay", f"/System/Library/Sounds/{sound}.aiff"], stderr=subprocess.DEVNULL)


def wav_bytes(int16: np.ndarray) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes(int16.tobytes())
    return buf.getvalue()


def send_to_claudia(int16: np.ndarray):
    if int16.size < SR // 3:            # < ~0.3s, ignore
        return
    try:
        req = urllib.request.Request(DAEMON + "/talk", data=wav_bytes(int16),
                                     headers={"Content-Type": "application/octet-stream"})
        urllib.request.urlopen(req, timeout=180).read()
    except Exception as e:
        print("send error:", e, flush=True)


def daemon_speaking() -> bool:
    try:
        with urllib.request.urlopen(DAEMON + "/health", timeout=3) as r:
            import json
            return bool(json.loads(r.read()).get("speaking"))
    except Exception:
        return False


class Recorder:
    """One always-open input stream; toggle `active` to capture into a buffer."""
    def __init__(self):
        self.frames = []
        self.active = False
        self._lock = threading.Lock()
        self.stream = sd.InputStream(samplerate=SR, channels=1, dtype="int16",
                                     blocksize=1280, callback=self._cb)
        self.stream.start()

    def _cb(self, indata, frames, t, status):
        if self.active:
            with self._lock:
                self.frames.append(indata[:, 0].copy())

    def start(self):
        with self._lock:
            self.frames = []
        self.active = True

    def stop(self) -> np.ndarray:
        self.active = False
        with self._lock:
            return np.concatenate(self.frames) if self.frames else np.zeros(0, dtype="int16")

    def record_until_silence(self) -> np.ndarray:
        """Used in conversation mode: capture one spoken turn (waits for speech, ends on silence)."""
        self.start()
        t0 = time.time()
        last_voice = None
        while True:
            time.sleep(0.08)
            with self._lock:
                buf = self.frames[-3:]
            if buf:
                rms = float(np.sqrt(np.mean(np.concatenate(buf).astype(np.float32) ** 2)))
                if rms > SILENCE_RMS:
                    last_voice = time.time()
            now = time.time()
            if last_voice and now - last_voice > SILENCE_HANG:
                break
            if last_voice is None and now - t0 > 6:      # no speech at all -> give up this turn
                break
            if now - t0 > MAX_TURN:
                break
        return self.stop()


class HotkeyApp:
    def __init__(self):
        self.rec = Recorder()
        self.down_at = 0.0
        self.is_down = False
        self.holding = False
        self.last_tap = 0.0
        self.conversation = False
        self._conv_thread = None
        print(f"[hotkey] ready. HOLD {HOTKEY_NAME} to talk; DOUBLE-TAP for conversation mode.", flush=True)

    def on_press(self, key):
        if key != HOTKEY or self.is_down:
            return
        self.is_down = True
        self.down_at = time.time()
        if not self.conversation:
            self.holding = True
            self.rec.start()            # begin capturing; we decide on release if it was a hold

    def on_release(self, key):
        if key != HOTKEY or not self.is_down:
            return
        self.is_down = False
        dur = time.time() - self.down_at
        if self.holding:
            audio = self.rec.stop()
            self.holding = False
            if dur >= HOLD_THRESHOLD:    # a real hold -> push-to-talk, send it
                cue("Pop")
                threading.Thread(target=send_to_claudia, args=(audio,), daemon=True).start()
                return
        # short press => a tap; check for double-tap
        now = time.time()
        if now - self.last_tap < DOUBLE_TAP:
            self.toggle_conversation()
            self.last_tap = 0.0
        else:
            self.last_tap = now

    def toggle_conversation(self):
        if self.conversation:
            self.conversation = False
            cue("Submarine")
            print("[hotkey] conversation mode OFF", flush=True)
        else:
            self.conversation = True
            cue("Glass")
            print("[hotkey] conversation mode ON — just talk", flush=True)
            self._conv_thread = threading.Thread(target=self._conversation_loop, daemon=True)
            self._conv_thread.start()

    def _conversation_loop(self):
        while self.conversation:
            if daemon_speaking():
                time.sleep(0.3)
                continue
            audio = self.rec.record_until_silence()
            if not self.conversation:
                break
            if audio.size > SR // 3:
                send_to_claudia(audio)
                time.sleep(0.6)
                while self.conversation and daemon_speaking():
                    time.sleep(0.2)

    def run(self):
        try:
            from ApplicationServices import AXIsProcessTrusted
            if not AXIsProcessTrusted():
                print("[hotkey] ⚠️  Accessibility permission NOT granted for this app — keys won't be "
                      "seen. Grant it in System Settings → Privacy & Security → Accessibility, then "
                      "restart this.", flush=True)
        except Exception:
            pass
        with keyboard.Listener(on_press=self.on_press, on_release=self.on_release) as listener:
            listener.join()


if __name__ == "__main__":
    try:
        HotkeyApp().run()
    except KeyboardInterrupt:
        sys.exit(0)
