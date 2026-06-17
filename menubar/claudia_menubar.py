#!/usr/bin/env python3
"""Optional menu-bar presence for Claudia (the 'always there' Jarvis feel).

OPTIONAL — not installed by default (keeps the base install dependency-light). To use:
    python3 -m venv menubar/.venv && menubar/.venv/bin/pip install rumps
    menubar/.venv/bin/python menubar/claudia_menubar.py

Gives a menu-bar item with: mute/unmute, speed presets, verbosity, speak clipboard, open panel.
All it does is call the local daemon's HTTP API, so it stays a thin client.
"""
import json
import subprocess
import urllib.request

import rumps

DAEMON = "http://127.0.0.1:4242"


def call(method, path, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(DAEMON + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


class Claudia(rumps.App):
    def __init__(self):
        super().__init__("◉", quit_button="Quit Claudia")
        self.mute_item = rumps.MenuItem("Mute", callback=self.toggle_mute)
        self.menu = [
            self.mute_item, None,
            rumps.MenuItem("Speak clipboard", callback=self.speak_clip),
            rumps.MenuItem("Stop speaking", callback=lambda _: call("POST", "/stop", {})), None,
            ("Speed", [rumps.MenuItem(f"{s:.2f}x", callback=self.set_speed)
                       for s in (0.75, 1.0, 1.25, 1.5, 2.0)]),
            ("Verbosity", [rumps.MenuItem(v.title(), callback=self.set_verbosity)
                           for v in ("verbatim", "summary", "headline")]), None,
            rumps.MenuItem("Open control panel", callback=lambda _: subprocess.run(["open", DAEMON])),
        ]
        rumps.Timer(self.refresh, 4).start()

    def refresh(self, _=None):
        try:
            c = call("GET", "/config")
            muted = c.get("muted")
            self.title = "○" if muted else "◉"
            self.mute_item.title = "Unmute" if muted else "Mute"
        except Exception:
            self.title = "◌"  # daemon down

    def toggle_mute(self, _):
        try:
            c = call("GET", "/config")
            call("POST", "/config", {"muted": not c.get("muted")})
            self.refresh()
        except Exception:
            pass

    def speak_clip(self, _):
        subprocess.run(["bash", "-lc",
                        "pbpaste | /opt/homebrew/bin/claudia read"])

    def set_speed(self, item):
        call("POST", "/config", {"rate": float(item.title.replace("x", ""))})

    def set_verbosity(self, item):
        call("POST", "/config", {"verbosity": item.title.lower()})


if __name__ == "__main__":
    Claudia().run()
