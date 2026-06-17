# Claudia — backlog

Captured from Ben's feedback; not yet built (or only partially).

## UI / presence (Ben: "some kind of user interface you can easily see and click on")
- [ ] A clear, always-visible, **clickable** presence — bigger/more obvious than the current menu-bar
      glyph. Options: a proper status menu-bar item with a real icon (not a unicode glyph), or a small
      floating always-on-top pill. Should show at a glance: On / Muted / Speaking / **On a call (silenced)**,
      and one-click mute + push-to-talk + conversation toggle.
- [ ] Menu-bar app packaged as a real `.app` (so Accessibility/Automation perms attach to *it*, and it
      can auto-start cleanly).
- [ ] Menu-bar toggles for: call-guard, conversation mode, hotkey on/off.

## "No surprises while on a call" (partially built)
- [x] Call-guard: auto-silence while in a call (currently detects Zoom meetings via the `CptHost`
      process — permission-free). Manual mute is the guaranteed control.
- [ ] Broaden detection: Google Meet / Teams / Webex / FaceTime active-call signals; ideally a true
      "microphone in use by another app" check (needs more work — CoreAudio / TCC).
- [ ] Make Claude-Code auto-narration explicitly opt-in per project, so it never surprises by default.
- [ ] Visible "silenced because you're on a call" indicator + a one-tap override.

## Voice / agent
- [ ] Faster agent brain (qwen2.5:7b) — pull in progress; swap default when ready.
- [ ] Barge-in in conversation mode (interrupt Claudia by talking).
- [ ] Sub-250ms Kyutai streaming via aggressive quantization.
- [ ] Approval flow for write/destructive actions (currently blocked outright).

## Access / deploy (needs Ben's accounts)
- [ ] Cloudflare Access + Google SSO deploy (docs/SSO-SETUP.md) — needs a dedicated CF domain.
- [ ] Publish to Rival.io (rival/PUBLISH.md) — needs Rival account.
- [ ] Drop the Vercel dependency once SSO + daemon-served UI is live (daemon serves its own HUD).
