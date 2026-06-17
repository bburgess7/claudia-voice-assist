#!/usr/bin/env python3
"""Claudia.app — the always-visible menu-bar app + the global backtick hotkey, in ONE process.

So a single Accessibility grant (and one Microphone grant) covers both, and you always have a visible,
clickable control: status at a glance, mute, conversation toggle, "Ask Claudia…", open panel.

Menu-bar title shows state:  ◉ on · 🔇 muted · 🎙️ conversation · ◌◍◎ speaking · ⚠ daemon off.
"""
import json
import os
import subprocess
import sys
import threading
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # find the hotkey pkg

import rumps
from hotkey.talk_hotkey import Hotkey, prompt_accessibility
from app.floating import FloatingWidget

DAEMON = os.environ.get("CLAUDIA_URL", "http://127.0.0.1:4242")


def call(method, path, payload=None, timeout=8):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(DAEMON + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


class ClaudiaApp(rumps.App):
    def __init__(self):
        super().__init__("◉", quit_button=None)
        self.hotkey = Hotkey()
        self.status_item = rumps.MenuItem("Starting…")
        self.mute_item = rumps.MenuItem("Mute", callback=self.toggle_mute)
        self.conv_item = rumps.MenuItem("Conversation mode", callback=self.toggle_conv)
        self.menu = [
            self.status_item, None,
            self.mute_item, self.conv_item,
            rumps.MenuItem("Ask Claudia…", callback=self.ask),
            rumps.MenuItem("Stop speaking", callback=lambda _: self._safe(call, "POST", "/stop", {})), None,
            rumps.MenuItem("Open control panel", callback=lambda _: subprocess.run(["open", DAEMON])),
            rumps.MenuItem("Pair a phone", callback=lambda _: subprocess.run(["open", DAEMON])), None,
            rumps.MenuItem("Quit Claudia", callback=rumps.quit_application),
        ]
        prompt_accessibility()                       # pop the macOS permission prompt if needed
        self.hotkey_ok = self.hotkey.install()       # host the key tap on the main run loop
        self._spin = 0
        self.widget = None                           # floating dot, created once the loop is running
        rumps.Timer(self.refresh, 2).start()

    def _safe(self, fn, *a):
        try:
            return fn(*a)
        except Exception:
            return None

    def refresh(self, _=None):
        if self.widget is None:
            try:
                self.widget = FloatingWidget(self)
            except Exception:
                self.widget = False                  # don't keep retrying if it can't be created
        state = "off"
        try:
            h = call("GET", "/health", timeout=3)
            c = call("GET", "/config", timeout=3)
            muted = c.get("muted")
            if not self.hotkey_ok:
                self.title = "🔑"; self.status_item.title = "Grant Accessibility, then relaunch (hotkey off)"
                state = "nokey"
            elif muted:
                self.title = "🔇"; self.status_item.title = "Muted — tap to unmute"; state = "muted"
            elif self.hotkey.conversation:
                self.title = "🎙️"; self.status_item.title = "Conversation mode — just talk"; state = "on"
            elif h.get("speaking"):
                self._spin = (self._spin + 1) % 3
                self.title = "◌◍◎"[self._spin]; self.status_item.title = "Speaking…"; state = "speaking"
            else:
                self.title = "◉"; self.status_item.title = f"On · {c.get('engine')} · hold ` to talk"; state = "on"
            self.mute_item.title = "Unmute" if muted else "Mute"
            self.conv_item.state = 1 if self.hotkey.conversation else 0
        except Exception:
            self.title = "⚠"; self.status_item.title = "Daemon off — run start.sh"; state = "off"
        if self.widget:
            try:
                self.widget.set_state(state)
            except Exception:
                pass

    def toggle_mute(self, _):
        c = self._safe(call, "GET", "/config") or {}
        self._safe(call, "POST", "/config", {"muted": not c.get("muted")})
        self.refresh()

    def toggle_conv(self, _):
        self.hotkey.toggle_conversation()
        self.refresh()

    def ask(self, _):
        w = rumps.Window(title="Ask Claudia", message="She'll act on your Mac and speak the result.",
                         default_text="", ok="Ask", cancel="Cancel", dimensions=(320, 24))
        r = w.run()
        if r.clicked and r.text.strip():
            threading.Thread(target=lambda: self._safe(call, "POST", "/ask",
                                                       {"text": r.text.strip()}, 180), daemon=True).start()


if __name__ == "__main__":
    ClaudiaApp().run()
