# Stable phone URL (A) — Cloudflare named tunnel, one-time setup

The quick tunnel (`scripts/tunnel.sh`) gives a NEW url each run. A **named tunnel** gives a permanent
URL like `https://claudia.yourdomain.com`, so you pair the phone once and never re-link. This needs a
domain whose DNS is on **Cloudflare**.

> ⚠️ **Don't use clawdiaventures.com or benefitswire.com for this.** Their DNS is on GoDaddy and is
> wired to Resend (the daily-log email). Moving them to Cloudflare would disrupt that email. Use a
> **separate/dedicated domain** added to Cloudflare's free plan (or a spare you own).

## One-time setup (needs your Cloudflare login — ~5 min)
```bash
# 1. Add your chosen domain to Cloudflare (free plan) and switch its nameservers to Cloudflare's.
#    (Cloudflare dashboard → Add a site → follow the nameserver steps.)

# 2. Authenticate cloudflared with your Cloudflare account (opens a browser):
cloudflared tunnel login

# 3. Create the tunnel (writes credentials to ~/.cloudflared/):
cloudflared tunnel create claudia

# 4. Point a hostname at it (creates the DNS record automatically):
cloudflared tunnel route dns claudia claudia.yourdomain.com
```

## Run it (every time, or via launchd)
```bash
CLAUDIA_HOSTNAME=claudia.yourdomain.com bash scripts/tunnel-named.sh
```
This registers the stable URL with the daemon, so the **"Pair a phone" QR** on the Mac encodes
`https://claudia.yourdomain.com` — scan once, done forever. Add it to the launchd plist to keep it up.

## If you'd rather I do it
Run step 2 (`cloudflared tunnel login`) yourself (it needs your browser), then tell me your chosen
hostname and I'll do steps 3–4 and wire `tunnel-named.sh` into launchd.
