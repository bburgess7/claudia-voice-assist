# Publishing Claudia to Rival.io — exact steps

Rival (CortexOne) publishing is **UI-only** — there's no API/CLI to publish, so these steps need your
account. Everything is prepared; this is ~10 minutes of clicks. (Happy to drive it via the browser
once you're logged in — just say so.)

## What we publish
Rival has **no voice layer**, so we publish Claudia's *brain*, two ways:
- **A Function tool** — the speak-ready summarizer (`rival/cortexone_function.py`). Reusable by any
  Rival agent: text in → spoken-style summary out, with secrets/code redacted.
- **An Agent** — the Claudia persona + guardrails (`rival/AGENT.md`) that calls that tool.

## Step 1 — account
1. Go to **https://cortexone.rival.io**, sign up (email + org), verify phone ($10 starter credit).

## Step 2 — publish the Function tool
1. Studio → **New Tool → Function** (Python 3.13).
2. Main file `cortexone_function.py`: paste the contents of `rival/cortexone_function.py`.
3. `requirements.txt`: paste `rival/requirements.txt` (stdlib only).
4. **Environment Secrets** (so it can summarize in the cloud, where there's no local Ollama):
   - `OPENAI_BASE_URL` = `https://openrouter.ai/api/v1`  (you already use OpenRouter)
   - `OPENAI_API_KEY`  = your OpenRouter key
   - `CLAUDIA_BRAIN`   = e.g. `openai/gpt-4o-mini` (or any OpenRouter model)
5. Test with event `{"text":"Refactored auth. \`\`\`x=1\`\`\` 18 tests passed. Deploy?","mode":"summary"}`
   → expect `{"spoken":"Added/refactored… 18 tests passed. Deploy?"}` (no code, no secrets).
6. **Publish** → visibility **Public** (or Organizational) → semver `1.0.0` → release notes.

## Step 3 — invoke it (to "see how it works")
```bash
curl -X POST "https://cortexconnect.rival.io/api/v1/functions/<FUNCTION_ID>/1.0.0/invoke" \
  -H "Authorization: <your-api-key>" -H "Content-Type: application/json" \
  -d '{"event":{"text":"<paste some Claude Code output>","mode":"headline"}}'
```
(API key: Workspace Settings → API. Note: NO "Bearer" prefix.) The `body` field is a JSON string —
parse it to get `spoken`.

## Step 4 — the Agent (optional)
Studio → **New Agent**. Fill the fields straight from `rival/AGENT.md`:
Instructions, Persona, Guardrails (the table), attach the **claudia_summarize** tool under Tools.
Publish.

## Closing the loop back to your local voice
Your local Claudia can call the published Rival tool (cloud brain) and speak the result:
```bash
SPOKEN=$(curl -s -X POST ".../invoke" -H "Authorization: <key>" \
  -d '{"event":{"text":"...","mode":"summary"}}' | python3 -c 'import sys,json;print(json.loads(json.load(sys.stdin)["body"])["spoken"])')
claudia read "$SPOKEN"
```
That's the full circle: Rival-hosted brain → local voice.
