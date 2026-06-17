#!/usr/bin/env python3
"""Claudia's menu-bar presence — so you can always SEE she's on and control her in one click.

Title icon tells you the state at a glance:
    ◉  on (idle)      ◌◍◎  speaking (animates)      ○  muted      ⚠  daemon off

Menu: a status line, a big Mute/Unmute, "Ask Claudia…" (type a request — she acts on your Mac and
speaks the result), Speak clipboard, Stop, Speed, Open panel, Pair a phone, Quit.

Install + run:  bash scripts/setup-menubar.sh   (creates a venv with rumps and launches it)
"""
import json
import subprocess
import threading
import urllib.request

import rumps

DAEMON = "http://127.0.0.1:4242"
CLI = "/opt/homebrew/bin/claudia"


def call(method, path, payload=None, timeout=10):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(DAEMON + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


class Claudia(rumps.App):
    def __init__(self):
        super().__init__("◌", quit_button=None)
        self.status_item = rumps.MenuItem("Starting…")
        self.mute_item = rumps.MenuItem("Mute", callback=self.toggle_mute)
        self.menu = [
            self.status_item, None,
            self.mute_item,
            rumps.MenuItem("Ask Claudia…", callback=self.ask),
            rumps.MenuItem("Speak clipboard", callback=self.speak_clip),
            rumps.MenuItem("Stop speaking", callback=lambda _: call("POST", "/stop", {})), None,
            ("Speed", [rumps.MenuItem(f"{s:.2f}x", callback=self.set_speed)
                       for s in (0.75, 1.0, 1.25, 1.5, 2.0)]),
            ("Verbosity", [rumps.MenuItem(v.title(), callback=self.set_verbosity)
                           for v in ("verbatim", "summary", "headline")]), None,
            rumps.MenuItem("Open control panel", callback=lambda _: subprocess.run(["open", DAEMON])),
            rumps.MenuItem("Pair a phone", callback=self.pair), None,
            rumps.MenuItem("Quit Claudia (menu only)", callback=rumps.quit_application),
        ]
        self._spin = 0
        rumps.Timer(self.refresh, 2).start()

    def refresh(self, _=None):
        try:
            h = call("GET", "/health", timeout=3)
            c = call("GET", "/config", timeout=3)
            muted = c.get("muted")
            if muted:
                self.title = "○"; self.status_item.title = "Muted — not speaking"
            elif h.get("speaking"):
                self._spin = (self._spin + 1) % 3
                self.title = "◌◍◎"[self._spin]; self.status_item.title = "Speaking…"
            else:
                self.title = "◉"; self.status_item.title = f"On · {c.get('engine')} · {c.get('voice')}"
            self.mute_item.title = "Unmute" if muted else "Mute"
        except Exception:
            self.title = "⚠"; self.status_item.title = "Daemon off — run start.sh"

    def toggle_mute(self, _):
        try:
            c = call("GET", "/config")
            call("POST", "/config", {"muted": not c.get("muted")})
            self.refresh()
        except Exception:
            pass

    def ask(self, _):
        w = rumps.Window(title="Ask Claudia", message="She'll act on your Mac and speak the result.",
                         default_text="", ok="Ask", cancel="Cancel", dimensions=(320, 24))
        resp = w.run()
        if resp.clicked and resp.text.strip():
            threading.Thread(target=lambda: call("POST", "/ask", {"text": resp.text.strip()},
                                                 timeout=180), daemon=True).start()

    def pair(self, _):
        subprocess.run(["open", DAEMON])  # the HUD has the "Pair a phone" QR button

    def speak_clip(self, _):
        subprocess.run(["bash", "-lc", f"pbpaste | {CLI} read"])

    def set_speed(self, item):
        call("POST", "/config", {"rate": float(item.title.replace("x", ""))})

    def set_verbosity(self, item):
        call("POST", "/config", {"verbosity": item.title.lower()})


if __name__ == "__main__":
    Claudia().run()
