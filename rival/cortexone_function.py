"""Rival.io Function tool — Claudia's "speak-ready summarizer" as a publishable Rival capability.

This is the portable core of Claudia (Goal 2). Rival Functions run in the cloud and can't reach a
local Ollama, so this mirrors the local summarizer's logic but calls an OpenAI-compatible chat API
(set OPENAI_BASE_URL + OPENAI_API_KEY as Rival Environment Secrets — e.g. OpenRouter). It degrades
to deterministic markup-stripping if no key is set, so it never hard-fails.

Rival entry contract: cortexone_handler(event, context) -> {"statusCode", "body"}.
  event: {"text": str, "mode": "summary"|"headline"|"verbatim"}
  body:  {"spoken": str}

requirements.txt: (none — stdlib only)
"""
import json
import os
import re
import urllib.request

SYSTEM = (
    "You convert developer-tool and assistant output into a brief SPOKEN update for someone "
    "listening hands-free. Say only what a person would want to HEAR: decisions, results, what "
    "changed, errors, blocking questions, next step. NEVER read code, file contents, diffs, logs, "
    "URLs, or file paths. No markdown, no symbols, no lists. Plain natural sentences. Output ONLY "
    "the spoken text — no preamble, no labels."
)


def _strip(text):
    text = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
    text = re.sub(r"`[^`]+`", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"^[#>\-\*\+\s]+", "", text, flags=re.MULTILINE)
    text = re.sub(r"[*_#`>|]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _llm(instruction, text):
    base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    key = os.environ.get("OPENAI_API_KEY")
    model = os.environ.get("CLAUDIA_BRAIN", "gpt-4o-mini")
    if not key:
        return None
    body = json.dumps({
        "model": model,
        "messages": [{"role": "system", "content": SYSTEM},
                     {"role": "user", "content": f"{instruction}\n\n{text[:6000]}"}],
        "temperature": 0.2, "max_tokens": 200,
    }).encode()
    req = urllib.request.Request(base + "/chat/completions", data=body, headers={
        "Content-Type": "application/json", "Authorization": f"Bearer {key}"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())["choices"][0]["message"]["content"].strip()
    except Exception:
        return None


def to_speech(text, mode="summary"):
    text = (text or "").strip()
    if not text:
        return ""
    if mode == "verbatim":
        return _strip(text)
    target = "a single short sentence" if mode == "headline" else "at most two or three sentences"
    out = _llm(f"Rewrite the following as {target} to be spoken aloud. Drop all code and file "
               f"names; keep only what changed, the result, and any question.", text)
    if out:
        return _strip(out)
    parts = re.split(r"(?<=[.!?])\s+", _strip(text))
    return " ".join(parts[: 1 if mode == "headline" else 3]).strip()


def cortexone_handler(event, context):
    text = event.get("text", "")
    mode = event.get("mode", "summary")
    return {"statusCode": 200, "body": {"spoken": to_speech(text, mode)}}


if __name__ == "__main__":  # local smoke test
    print(cortexone_handler(
        {"text": "Refactored auth. ```py\nx=1\n``` 18 tests passed. Deploy?", "mode": "summary"}, {}))
