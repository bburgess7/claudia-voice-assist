# Claudia 🔴

A local, **Jarvis-style conversational voice layer** for your Mac. She speaks back — fully on-device —
and she says *only what matters*: in Claude Code she narrates the result ("18 tests passed, deploy?"),
not the raw code (and never reads secrets, keys, or file paths aloud — that's enforced, with tests).
Talk to her with a wake word, control her from a HUD, and reach her from your phone by scanning a QR.

Built and tested on an M4 Pro / 48GB. Everything runs locally; the only path in from outside is a
tunnel you start, gated by a secret.

## Install (anyone, fresh Mac)
```bash
git clone https://github.com/bburgess7/claudia-voice-assist
cd claudia-voice-assist && bash setup.sh        # daemon + Kokoro voice + CLI
bash scripts/start.sh                            # then open http://127.0.0.1:4242
```

---

## What it does (Goal 1)

- 🗣️ **Talks back** — three swappable, isolated engines: **Kokoro** (default; kokoro-onnx, ~340MB,
  fast and dependable), **Kyutai** (moshi-mlx 1.6B, richer voice; heavier/slower — `scripts/kyutai.sh`),
  and macOS `say` (zero-dep fallback). Pick live in the HUD.
- 🧠 **Reads only the critical bits — and never secrets** — a local `llama3.2:3b` filter turns
  code-heavy output into a spoken headline. Secrets/keys/tokens/file-paths are **redacted before the
  model sees them and again on output**; pure code becomes "made some code changes." Levels:
  `verbatim` / `summary` / `headline`. (See `tests/test_summarizer.py`.)
- 🎚️ **Live speed + voice control** — a HUD with a rate slider (0.5×–2×), voice picker, verbosity,
  engine, mute, and a reactive ember orb that lights up when she speaks.
- 👂 **"Hey Claudia" → conversation** — default `keyword` wake mode spots **"hey claudia"** with no
  training; single-breath commands work ("Hey Claudia, what's the status?"). `oww` mode uses
  openWakeWord "hey jarvis" for lowest CPU. Then STT → local LLM → spoken reply (`scripts/listen.sh`).
  *(Verify with a real mic; the loop is built and component-tested but mic round-trips depend on your setup.)*
- 🌍 **Global** — `claudia` CLI on PATH and a Claude Code hook so every session narrates itself.
  Also a speak-the-selection hotkey (one-time macOS Shortcut) and an optional menu-bar app.
- 📱 **Mobile, scan to pair** — the HUD is **hosted on Vercel**; start `scripts/tunnel.sh`, tap
  **"Pair a phone"** on the Mac, and scan the QR — no URLs or secrets to type.
  Live: https://claudia-voice-benmburgess-8525s-projects.vercel.app

## Portable & extensible (Goal 2)

Claudia's capabilities are exposed as a stdlib **MCP server** (`rival/mcp_server.py`) — any agent
(Claude Code, Cursor, a **Rival.io** agent) can drive her. The summarizer also ships as a Rival
**Function** (`rival/cortexone_function.py`), and `rival/AGENT.md` is a paste-ready manifest mapping
Claudia onto Rival's fields. (Rival has no voice layer — the voice loop stays local; the brain ports.)

---

## Architecture — why it's robust

```
   any source ──► claudiad (lean daemon, FastAPI+WS) ──► local speakers
   • Claude Code hook        │  • summarizer (Ollama)      └► WS audio ─► phone/PWA
   • claudia CLI / selection │  • pluggable TTS engine
   • mic (wake word)         │  • serialized speech queue
                             ▼
              Kokoro sidecar (.venv-kokoro, isolated)   ← never destabilizes the daemon
              Listen sidecar (.venv-listen, isolated)
```

The daemon carries **no ML dependencies**. Each audio engine lives in its **own venv** behind an
HTTP/subprocess boundary, so dependency churn in the audio stack can never break the core voice or
the daemon. (This is why the install fought mlx and won: Kokoro runs on stable ONNX, isolated.)

## Quick start

```bash
# 1. start the voice (sidecar + daemon)
bash scripts/start.sh                 # CLAUDIA_HOST=0.0.0.0 to reach it over Tailscale

# 2. try it
claudia say "I refactored auth and the tests pass — deploy?"   # speaks the gist
open http://127.0.0.1:4242            # the control panel HUD

# 3. talk to her (optional)
bash scripts/listen.sh                # say "hey jarvis"

# 4. auto-start at login (optional)
bash scripts/install-launchd.sh
```

Prereqs: Python 3.12 (Homebrew), Ollama running with `llama3.2:3b`. The Kokoro model + voices are
fetched into `.venv-kokoro/` (one-time).

## Layout

| Path | What |
|---|---|
| `daemon/` | the lean FastAPI/WS daemon (no ML deps) — server, config, speech queue, summarizer |
| `daemon/engines/` | pluggable TTS: `macos_say`, `kokoro` (HTTP client to sidecar) |
| `engines_sidecar/kokoro_server.py` | Kokoro TTS, isolated venv, kept warm |
| `listen/listen.py` | wake-word → STT → brain → speak loop (isolated venv) |
| `web/public/` | control panel + mobile PWA (single self-contained `index.html`) |
| `hooks/claude_code_hook.py` | Claude Code Stop/Notification → spoken summary |
| `rival/` | MCP server + Rival Function + `AGENT.md` (Goal 2 portability) |
| `scripts/` | `start`/`stop`/`listen`/`install-launchd`/`speak-selection` + `claudia` CLI |
| `docs/` | `ARCHITECTURE.md`, `GLOBAL.md` (hotkeys/mobile/Tailscale), `DESIGN.md`, `PRODUCT.md` |

## Config
Live config in `~/.claudia/config.json` (engine, voice, rate, verbosity, muted, summarizer_model,
wake_word, shared_secret). Change it from the HUD, the `claudia` CLI, the MCP tools, or any client —
changes broadcast to all connected surfaces.
