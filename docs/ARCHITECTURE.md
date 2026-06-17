# Claudia — a local, Jarvis-style conversational voice layer

**Goal (G1):** A locally-hosted voice AI on the Mac that *talks back* — natural, conversational,
low-latency, never slows the machine. Speaks a **smart summary** of what's happening (e.g. in Claude
Code, it reads the critical takeaways, not raw code). Adjustable speaking rate via a UI. Bonus: wake
word "Hey Claudia", global across all apps, reachable from other computers and phone over Tailscale.

**Goal (G2):** Portable & extensible — capture the agent definition so it can be recreated/ported to
Rival.io.

## The shape

```
                         ┌──────────────────────────────────────────────┐
                         │  claudiad  (local daemon, FastAPI + WS)       │
   any app / source ───► │                                              │
   • Claude Code hook    │   /speak  ──► Summarizer ──► TTS engine ──►   │ ──► local speakers
   • selected text       │             (LLM filter)    (pluggable)      │ ──► WS audio out
   • CLI `claudia say`   │                                              │      (remote/mobile)
   • mic (wake word)  ──►│   /listen ◄── STT  ◄── wake word ("Claudia") │ ◄── WS mic in
                         │                                              │
                         │   /config  speed, voice, verbosity, on/off   │
                         └──────────────────────────────────────────────┘
                                        ▲                    ▲
                         control panel (web)        mobile PWA over Tailscale
```

### Components

1. **`claudiad` daemon** (Python, `daemon/`) — one long-running local service.
   - `POST /speak {text, mode}` — the universal "say this" entrypoint. `mode` selects how aggressively
     to summarize (`verbatim` | `summary` | `headline`).
   - **Summarizer** — an LLM pass (local via Ollama, or Claude) that rewrites input into *spoken* form:
     drop code blocks, file dumps, logs; keep decisions, results, questions, next steps. This is the
     "don't read everything" brain. Prompted to output speech-ready prose (no markdown, no symbols).
   - **TTS engine** (`daemon/engines/`) — pluggable behind one interface (`synthesize(text, voice,
     rate) -> audio stream`). Default engine = fast/real-time; optional upgrade engine = max-natural.
     Engine choice pending research agent.
   - **STT + wake word** — streaming local STT for the conversational loop; "Hey Claudia" wake word.
   - **WebSocket** — streams synthesized audio to remote/mobile clients and accepts mic audio back.

2. **Claude Code integration** (`hooks/`) — uses Claude Code hooks (PostToolUse / Stop / Notification)
   to POST a *summary* of activity to `/speak`. So Claudia narrates "Created the auth route and ran the
   tests — 3 passed" instead of reading the diff. Verbosity is user-tunable.

3. **Control panel** (`web/`) — the UI. Speed slider (0.5×–2×), voice picker, verbosity, push-to-talk,
   on/off, live transcript. Also serves as the **mobile PWA** (installable, works over Tailscale).
   Design: distinctive, not AI-slop — driven by the design skills. (See DESIGN.md.)

4. **Global OS hooks** — menu-bar control + global hotkey + "speak selection." macOS-native bits via
   a small helper.

5. **Portability layer** (`docs/AGENT.md`) — the agent expressed as a portable manifest (system prompt,
   tools, voice config, summarizer policy) so it can be ported to Rival.io. Pending research agent.

## Principles
- **Never block the machine.** TTS/STT run in the daemon, work queued, models sized to stay real-time
  on M4 Pro without thrashing. Default engine chosen for low, steady resource use.
- **One pluggable interface per concern** (TTS, STT, summarizer, wake word) so engines are swappable
  and the whole thing is portable.
- **Local-first, Tailscale for reach.** No cloud dependency for the core voice loop; Tailscale exposes
  the same daemon to laptop, other Macs, and phone. No ports opened to the public internet.
- **Security:** only vetted, permissively-licensed, actively-maintained deps. Daemon binds to localhost
  + Tailscale interface only; optional shared-secret on the WS.
