# Using Claudia everywhere — global, hotkeys, mobile, Tailscale

## From any terminal
The `claudia` CLI is symlinked onto your PATH:
```
claudia say "hello"          # speak (summarized per current verbosity)
echo "long text" | claudia say
claudia read "exact words"   # verbatim
claudia speed 1.5            # change speaking rate live
claudia mute / unmute
claudia stop                 # barge-in
claudia voices | config | status
```

## Speak the selection from ANY app (global hotkey)
`scripts/speak-selection.sh` reads your clipboard aloud. Bind it to a global hotkey with the macOS
**Shortcuts** app (no extra software, no accessibility hacks):

1. Shortcuts → new shortcut → add **Run Shell Script** action:
   `bash /Users/benburgess/dev/claudia/scripts/speak-selection.sh`
   (use `... speak-selection.sh summary` to summarize long passages instead of reading verbatim)
2. Shortcut → Details → **Add Keyboard Shortcut** → e.g. ⌃⌥S.
3. Now: select/copy text in any app, hit the hotkey → Claudia speaks it.

## Menu-bar app (optional)
A little ◉ in the menu bar (mute, speed, verbosity, speak clipboard, open panel). Optional so the base
install stays light:
```
python3 -m venv menubar/.venv && menubar/.venv/bin/pip install rumps
menubar/.venv/bin/python menubar/claudia_menubar.py
```

## In Claude Code (the flagship)
Installed globally in `~/.claude/settings.json` (Stop + Notification hooks → `hooks/claude_code_hook.py`).
When Claudia is running, each turn she speaks a **summary** of what Claude did — not the code — and
reads permission prompts aloud. Inert when the daemon is off or muted. Remove those two hook blocks to
disable.

## Phone + other computers (over Tailscale)
The control panel doubles as a mobile client and **plays audio in the browser** when opened remotely.

1. Bind the daemon to your Tailnet: set `CLAUDIA_HOST=0.0.0.0` (in the launchd plist, or
   `CLAUDIA_HOST=0.0.0.0 bash scripts/start.sh`).
2. **Set a shared secret first** (so only you can drive it):
   `claudia config` to view; `curl -X POST :4242/config -d '{"shared_secret":"<random>"}'`. Remote
   WS clients must send it in their hello frame (add `?secret=…` handling or paste it in — see note).
3. On your iPhone (same Tailnet), open `http://bens-macbook-pro:4242` (or the Tailscale IP
   `http://100.114.234.100:4242`). Tap **Share → Add to Home Screen** to install the PWA.
4. Remote clients connect with role `remote`, so audio streams to and plays on the phone; the Mac's
   own speakers stay quiet for that utterance.

Security: the daemon never opens a public internet port — Tailscale is the only path in, and the
shared secret gates the WebSocket. Keep `CLAUDIA_HOST=127.0.0.1` when you don't need remote.

## Auto-start at login
```
bash scripts/install-launchd.sh     # RunAtLoad + KeepAlive
```
