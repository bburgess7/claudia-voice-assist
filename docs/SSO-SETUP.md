# Super-secure SSO access from anywhere (Cloudflare Access + Google)

The goal: open the URL on any device → **Sign in with Google** (the only, obvious input) → you're in.
No secrets, no typing, and **only your Google account can reach it**. This is the shippable, secure
way to use Claudia from anywhere.

How it works: a Cloudflare **named tunnel** exposes your Mac at a stable URL; **Cloudflare Access**
(free Zero Trust) puts a Google login in front of it; the daemon trusts the verified email Access
injects (`cf-access-authenticated-user-email`) and rejects everything else. The daemon code + tests
for this are already in place (`tests/test_auth.py`) — this is the one-time Cloudflare setup.

> Needs a domain whose DNS is on Cloudflare. **Don't use clawdiaventures.com / benefitswire.com**
> (GoDaddy + Resend email). Use a dedicated domain — easiest is to **register one on Cloudflare
> Registrar** (auto-on-Cloudflare), e.g. `clawdia.app`.

## One-time setup (~10 min, needs your Cloudflare login)
```bash
# 0. Have a domain on Cloudflare (Registrar or "Add a site" + nameserver switch).

# 1. Tunnel
cloudflared tunnel login
cloudflared tunnel create claudia
cloudflared tunnel route dns claudia claudia.yourdomain.com
```
Then in the **Cloudflare dashboard → Zero Trust → Access**:
2. **Add an application → Self-hosted** → domain `claudia.yourdomain.com`.
3. **Policy**: Action *Allow*, Include → *Emails* → `you@gmail.com` (add any others you want).
4. Identity provider: **Google** (Zero Trust → Settings → Authentication → add Google — one-click).
5. Save.

## Wire the daemon to the SSO identity
```bash
claudia ... # or:
curl -s -X POST http://127.0.0.1:4242/config -d '{"access_email":"you@gmail.com","sso":true,"public_url":"https://claudia.yourdomain.com"}'
```
Now the **"Pair a phone" QR** encodes just `https://claudia.yourdomain.com` (no secret). Run the tunnel:
```bash
CLAUDIA_HOSTNAME=claudia.yourdomain.com bash scripts/tunnel-named.sh
```

## The end-user experience (you, or anyone you allowlist)
1. Scan the QR (or open the URL).
2. "Sign in with Google" → pick your account.
3. Claudia's HUD loads. Done. Works from any device, anywhere, no secret, fully gated to your account.

## Why it's secure
- No inbound ports on your Mac; the tunnel only makes **outbound** connections.
- Every remote request is gated by Google SSO at Cloudflare's edge; the daemon independently rejects
  any request whose `cf-access-authenticated-user-email` isn't your allowlisted address.
- Hardening option: verify the `Cf-Access-Jwt-Assertion` JWT against your team's public keys (the
  email header is sufficient behind Access, but JWT verification removes all trust in headers).

## If you'd rather I do it
Run `cloudflared tunnel login` (needs your browser) and add Google as an IdP in Zero Trust, then tell
me your domain + email — I'll do the tunnel/route/Access-app/daemon wiring and test it end to end.
