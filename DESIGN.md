# DESIGN.md — Claudia control panel

## Theme
Warm ember/oxblood HUD on architectural near-black. "A glowing coal in a dark workshop." Depth from
layered radial gradients, never flat. Dark is intrinsic (hands-free, low-light, evening use).

## Color (OKLCH)
- `--bg`        oklch(0.12 0.008 30)   — near-black, faintly warm
- `--bg-deep`   oklch(0.08 0.006 30)   — vignette floor
- `--surface`   oklch(0.17 0.012 30)   — raised panels
- `--surface-2` oklch(0.21 0.014 30)   — controls
- `--ink`       oklch(0.96 0.006 60)   — primary text (≥12:1 on bg)
- `--muted`     oklch(0.74 0.02 45)    — secondary text (≥4.5:1 on bg)
- `--primary`   oklch(0.55 0.17 22)    — oxblood crimson (the orb core, active states)
- `--primary-hi`oklch(0.64 0.19 25)    — brighter crimson for glow
- `--accent`    oklch(0.80 0.14 65)    — sharp warm amber/ember (highlights, focus, the "live" dot)
- `--line`      oklch(0.30 0.01 30)    — hairline borders

Strategy: **Committed-dark.** Crimson + amber carry identity; bg stays a true near-black so the glow
reads as light, not blood. Accent (amber) used sparingly — focus rings, the live indicator, the
active tick on sliders.

## Typography
- Display / UI: **Space Grotesk** (700/500/300) — distinctive geometric grotesque, not Inter.
- Mono: **JetBrains Mono** (400/600) — status line, transcript, numeric values, labels.
- Pairing axis: geometric-grotesque vs. mono (real contrast). Big weight jumps (300 vs 700).
- Wordmark "CLAUDIA" in tracked light weight; values & system text in mono.

## Motion
- Load: staggered reveal of header → orb → controls via `animation-delay` (ease-out-expo).
- Orb idle: slow 6s breathing scale + drifting inner gradient.
- Orb speaking: amplitude-reactive rings (real FFT when audio plays in-browser; smoothed synthetic
  amplitude when only a speaking flag is known).
- All gated behind `prefers-reduced-motion: reduce` (crossfade / static orb fallback).

## Components
- **Orb** — canvas focal point; concentric reactive rings around a crimson core with amber rim light.
- **Transcript** — mono, last spoken line large, prior lines fading above.
- **Rate slider** — the hero control; large track, amber tick, live `1.25×` mono readout.
- **Segmented controls** — verbosity, engine (pill segments, active = crimson fill).
- **Voice select** — styled native select (escapes overflow correctly).
- **Listen/Mute** — the single big primary toggle.
- **Speak box** — textarea + Speak + Stop.

## Layout
- Desktop: two zones — living focal column (orb + transcript) left/center, controls rail right.
- Mobile: single column, orb up top, controls stacked, big touch targets (≥44px).
- No card-in-card. Panels are surfaces with hairline tops, generous padding, varied rhythm.
