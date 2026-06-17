#!/usr/bin/env python3
"""Global push-to-talk hotkey for Claudia — default key: BACKTICK ` (the Discord/gaming PTT key).

  HOLD `         -> records while held, RELEASE sends it (push-to-talk).
  DOUBLE-TAP `   -> toggles hands-free CONVERSATION mode (talk, she replies, repeat; double-tap to stop).
  SINGLE tap `   -> types a normal backtick (re-injected), so you can still use it.

Smart conflict avoidance: when your FRONTMOST app is a code editor or terminal, ` is passed straight
through and types normally — so code fences ``` are never hijacked. Talk-mode only applies outside
those apps. Audio is captured locally and sent to /talk (local Whisper -> agent -> speaks). Nothing
leaves your Mac.

Uses a Quartz event tap (selective key consumption), so it needs ACCESSIBILITY permission for the app
that launches it. Run: bash scripts/setup-hotkey.sh.  Override key with CLAUDIA_HOTKEY_KEYCODE.
"""
import json
import os
import subprocess
import sys
import threading
import time
import urllib.request
import wave

import numpy as np
import sounddevice as sd
import Quartz
from AppKit import NSWorkspace

DAEMON = os.environ.get("CLAUDIA_URL", "http://127.0.0.1:4242")
KEYCODE = int(os.environ.get("CLAUDIA_HOTKEY_KEYCODE", "50"))   # 50 = grave/backtick on US layout
HOLD_THRESHOLD = 0.35
DOUBLE_TAP = 0.40
SR = 16000
SILENCE_RMS = 350
SILENCE_HANG = 0.9
MAX_TURN = 12.0

# When one of these is frontmost, ` types normally (don't hijack code fences / shell).
EDITOR_HINTS = ("cursor", "code", "visual studio", "terminal", "iterm", "warp", "xcode",
                "pycharm", "intellij", "webstorm", "sublime", "nova", "zed", "hyper", "kitty",
                "alacritty", "ghostty")


def cue(sound="Tink"):
    subprocess.run(["afplay", f"/System/Library/Sounds/{sound}.aiff"], stderr=subprocess.DEVNULL)


def wav_bytes(int16: np.ndarray) -> bytes:
    buf = __import__("io").BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes(int16.tobytes())
    return buf.getvalue()


def send_to_claudia(int16: np.ndarray):
    if int16.size < SR // 3:
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
            return bool(json.loads(r.read()).get("speaking"))
    except Exception:
        return False


class Recorder:
    def __init__(self):
        self.frames, self.active, self._lock = [], False, threading.Lock()
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
        self.start()
        t0, last_voice = time.time(), None
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
            if (last_voice is None and now - t0 > 6) or now - t0 > MAX_TURN:
                break
        return self.stop()


def prompt_accessibility() -> bool:
    """Actually POP the macOS 'allow accessibility' prompt (not the silent check). Returns trust state."""
    try:
        from ApplicationServices import AXIsProcessTrustedWithOptions
        # kAXTrustedCheckOptionPrompt -> True makes the system show the prompt + open the pane
        return bool(AXIsProcessTrustedWithOptions({"AXTrustedCheckOptionPrompt": True}))
    except Exception:
        try:
            from ApplicationServices import AXIsProcessTrusted
            return bool(AXIsProcessTrusted())
        except Exception:
            return False


def _frontmost_is_editor() -> bool:
    try:
        app = NSWorkspace.sharedWorkspace().frontmostApplication()
        name = (app.localizedName() or "").lower()
        return any(h in name for h in EDITOR_HINTS)
    except Exception:
        return False


class Hotkey:
    def __init__(self):
        self.rec = Recorder()
        self.is_down = False
        self.down_at = 0.0
        self.last_tap = 0.0
        self.conversation = False
        self._passthrough = 0   # count of our own re-injected ` events to let through

    def _reinject_grave(self):
        self._passthrough = 2
        for down in (True, False):
            e = Quartz.CGEventCreateKeyboardEvent(None, KEYCODE, down)
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, e)

    def callback(self, proxy, type_, event, refcon):
        try:
            keycode = Quartz.CGEventGetIntegerValueField(event, Quartz.kCGKeyboardEventKeycode)
        except Exception:
            return event
        if keycode != KEYCODE:
            return event
        if self._passthrough > 0:                       # our own re-injected backtick — let it type
            self._passthrough -= 1
            return event
        if not self.conversation and _frontmost_is_editor():
            return event                                # in an editor/terminal: ` types normally

        if type_ == Quartz.kCGEventKeyDown:
            if not self.is_down:
                self.is_down = True
                self.down_at = time.time()
                if not self.conversation:
                    self.rec.start()
            return None                                 # consume

        if type_ == Quartz.kCGEventKeyUp:
            self.is_down = False
            dur = time.time() - self.down_at
            if not self.conversation:
                audio = self.rec.stop()
                if dur >= HOLD_THRESHOLD:                # held -> push-to-talk
                    cue("Pop")
                    threading.Thread(target=send_to_claudia, args=(audio,), daemon=True).start()
                    return None
            now = time.time()
            if now - self.last_tap < DOUBLE_TAP:         # double-tap -> conversation toggle
                self.last_tap = 0.0
                self.toggle_conversation()
            else:
                self.last_tap = now
                if not self.conversation:
                    self._reinject_grave()               # single tap -> actually type a backtick
            return None
        return event

    def toggle_conversation(self):
        self.conversation = not self.conversation
        if self.conversation:
            cue("Glass"); print("[hotkey] conversation ON — just talk", flush=True)
            threading.Thread(target=self._conversation_loop, daemon=True).start()
        else:
            cue("Submarine"); print("[hotkey] conversation OFF", flush=True)

    def _conversation_loop(self):
        while self.conversation:
            if daemon_speaking():
                time.sleep(0.3); continue
            audio = self.rec.record_until_silence()
            if not self.conversation:
                break
            if audio.size > SR // 3:
                send_to_claudia(audio)
                time.sleep(0.6)
                while self.conversation and daemon_speaking():
                    time.sleep(0.2)

    def install(self, runloop=None) -> bool:
        """Create the key tap and add it to a run loop (default: the MAIN loop, so it can be hosted
        inside a menu-bar app). Returns True if the tap was created (i.e. Accessibility is granted)."""
        mask = Quartz.CGEventMaskBit(Quartz.kCGEventKeyDown) | Quartz.CGEventMaskBit(Quartz.kCGEventKeyUp)
        tap = Quartz.CGEventTapCreate(
            Quartz.kCGSessionEventTap, Quartz.kCGHeadInsertEventTap,
            Quartz.kCGEventTapOptionDefault, mask, self.callback, None)
        if not tap:
            return False
        src = Quartz.CFMachPortCreateRunLoopSource(None, tap, 0)
        Quartz.CFRunLoopAddSource(runloop or Quartz.CFRunLoopGetMain(), src,
                                  Quartz.kCFRunLoopCommonModes)
        Quartz.CGEventTapEnable(tap, True)
        self._tap, self._src = tap, src
        return True

    def run(self):
        prompt_accessibility()
        if not self.install(Quartz.CFRunLoopGetCurrent()):
            print("[hotkey] ⚠️  Could not create the key tap — grant ACCESSIBILITY permission to this "
                  "app (System Settings → Privacy & Security → Accessibility), then restart.", flush=True)
            return
        print("[hotkey] ready. HOLD ` to talk; DOUBLE-TAP ` for conversation. (` types normally in "
              "editors/terminals.)", flush=True)
        Quartz.CFRunLoopRun()


if __name__ == "__main__":
    try:
        Hotkey().run()
    except KeyboardInterrupt:
        sys.exit(0)
