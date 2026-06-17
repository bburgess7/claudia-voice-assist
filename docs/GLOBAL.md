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
   `bash /Users/benburgess/dev/claudia-voice-assist/scripts/speak-selection.sh`
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

## Phone + other computers (hosted web app + tunnel — no Tailscale)
The control panel is **deployed publicly on Vercel** and **plays audio in the browser** when opened
remotely. It reaches your Mac through a Cloudflare tunnel, gated by a shared secret.

**Hosted URL:** https://claudia-voice-benmburgess-8525s-projects.vercel.app
(redeploy after UI changes: `cd web/public && ~/.npm-global/bin/vercel deploy --prod --yes --scope benmburgess-8525s-projects`)

Steps:
1. Make sure the daemon is running locally (`bash scripts/start.sh`).
2. Start the tunnel: `bash scripts/tunnel.sh`. It auto-generates a shared secret if none is set and
   prints the public `https://…trycloudflare.com` URL plus the secret.
3. On your phone, open the Vercel URL above and **Add to Home Screen** to install the PWA.
4. On its **"Link to your Mac"** connect screen, paste the tunnel URL and the secret (stored on the
   phone only). Done — you control Claudia and hear her on the phone.

How the security works: the daemon only enforces the secret for **proxied/tunneled** requests
(they carry `cf-connecting-ip`/`x-forwarded-for`); direct local requests on the Mac stay open, so the
local panel never needs a secret. Remote clients connect with role `remote`, so audio streams to the
phone while the Mac stays quiet for that utterance.

Notes:
- Quick tunnels are ephemeral (new URL each run). For a **stable** URL, set up a Cloudflare *named*
  tunnel against one of your domains (e.g. clawdiaventures.com) — then the phone never needs re-linking.
- Testing the tunnel *from the Mac itself* can fail if Tailscale MagicDNS returns IPv6-only for
  `trycloudflare.com`; the phone (on its own network) is unaffected.
- LAN alternative (no tunnel, home only): `CLAUDIA_HOST=0.0.0.0 bash scripts/start.sh`, then on the
  same WiFi open `http://<mac-ip>:4242` and link to that URL.

## Auto-start at login
```
bash scripts/install-launchd.sh     # RunAtLoad + KeepAlive
```
