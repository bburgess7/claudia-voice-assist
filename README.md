# Claudia 🔴

A local, **Jarvis-style conversational voice layer** for your Mac. She speaks back — naturally,
fast, and fully on-device — and she says *only what matters*: in Claude Code she narrates the
result ("18 tests passed, deploy?"), not the raw code. Talk to her with a wake word, control her
from a HUD, and reach her from your phone over Tailscale.

Built for an M4 Pro / 48GB. Everything runs locally; Tailscale is the only path in from outside.

---

## What it does (Goal 1)

- 🗣️ **Talks back, naturally** — default voice **Kokoro** (kokoro-onnx, ~170MB, ~4× real-time,
  rock-solid). Swappable: macOS `say` (zero-dep fallback), Kyutai/Orpheus as upgrades.
- 🧠 **Reads only the critical bits** — an LLM filter (local `llama3.2:3b` via Ollama) turns
  code-heavy output into a spoken headline. Three levels: `verbatim` / `summary` / `headline`.
- 🎚️ **Live speed + voice control** — a sci-fi HUD with a rate slider (0.5×–2×), voice picker,
  verbosity, engine, mute, and a reactive ember orb that lights up when she speaks.
- 👂 **Wake word → conversation** — say **"hey jarvis"** ("hey claudia" trainable) and she listens,
  thinks (local LLM), and replies aloud. (`scripts/listen.sh`)
- 🌍 **Global** — `claudia` CLI on PATH, speak-the-selection hotkey, optional menu-bar app, and a
  Claude Code hook so every session narrates itself.
- 📱 **Mobile + remote** — the control panel is an installable PWA; opened over Tailscale it plays
  audio on the phone (role-aware, no echo on the Mac).

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
