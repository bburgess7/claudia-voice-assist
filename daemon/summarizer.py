"""Turn raw text (Claude Code output, notifications, selected text) into speech-ready prose.

The core of "don't read everything." Modes:
  verbatim  — just clean markdown/symbols so it reads naturally; no LLM.
  summary   — LLM condenses to the few things a human would want to HEAR (default).
  headline  — LLM reduces to a single spoken sentence.

Uses local Ollama if reachable; otherwise a deterministic rule-based fallback so the voice never
goes silent just because a model isn't loaded.
"""
from __future__ import annotations

import json
import re
import urllib.request
from typing import Optional

OLLAMA_CHAT_URL = "http://127.0.0.1:11434/api/chat"

SYSTEM = (
    "You convert developer-tool and AI-assistant output into a brief SPOKEN update for a software "
    "engineer who is listening hands-free, not looking at the screen. Say only what a person would "
    "want to HEAR: decisions made, results, what changed, errors, blocking questions, and the next "
    "step. NEVER read code, file contents, diffs, logs, stack traces, URLs, or file paths. No "
    "markdown, no symbols, no bullet points, no emoji. Expand abbreviations into spoken words. Use "
    "plain natural sentences. Be concise. Output ONLY the spoken text itself — no preamble, no "
    "labels, no quotation marks, no commentary."
)

# One-shot example delivered as a real user/assistant turn so small instruct models copy the
# FORMAT without echoing the framing.
EX_IN = ("I'll add the limiter. ```py\ndef f(): ...\n``` Wired it into api/send.py and added 4 tests "
         "in test_rl.py. Ran the suite: 18 passed, 1 failed on the burst test (off-by-one at the "
         "window boundary). Fix the boundary or loosen the test?")
EX_OUT = ("Added the rate limiter and four tests. Eighteen passed, but the burst test failed on an "
          "off-by-one at the window boundary. Want me to fix the boundary or loosen the test?")

_PREAMBLE = re.compile(
    r"^\s*(here(?:'s| is| are)[^:]*:|spoken( output)?:|sure[,!.]?|okay[,!.]?|output:)\s*",
    re.IGNORECASE)


def _strip_markup(text: str) -> str:
    text = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)          # fenced code -> drop
    text = re.sub(r"\(\s*code\s*\)", "", text, flags=re.IGNORECASE)  # any leaked placeholder
    text = re.sub(r"`[^`]+`", "", text)                              # inline code
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)                 # images
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)             # links -> label
    text = re.sub(r"https?://\S+", "", text)                         # bare urls
    text = re.sub(r"^[#>\-\*\+\s]+", "", text, flags=re.MULTILINE)   # md line prefixes
    text = re.sub(r"[*_#`>|]", "", text)                             # stray md symbols
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{2,}", ". ", text).replace("\n", " ")
    return text.strip()


def _ollama_chat(model: str, instruction: str, text: str, timeout: float = 20.0) -> Optional[str]:
    body = json.dumps({
        "model": model, "stream": False,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": f"{instruction}\n\n{EX_IN}"},
            {"role": "assistant", "content": EX_OUT},
            {"role": "user", "content": f"{instruction}\n\n{text[:6000]}"},
        ],
        "options": {"temperature": 0.2, "num_predict": 200},
    }).encode()
    req = urllib.request.Request(OLLAMA_CHAT_URL, data=body,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            out = json.loads(r.read()).get("message", {}).get("content", "").strip()
        return _PREAMBLE.sub("", out).strip().strip('"')
    except Exception:
        return None


def to_speech(text: str, mode: str = "summary", model: str = "qwen2.5-coder:1.5b") -> str:
    text = (text or "").strip()
    if not text:
        return ""
    if mode == "verbatim":
        return _strip_markup(text)

    target = "a single short sentence" if mode == "headline" else "at most two or three sentences"
    instruction = (f"Rewrite the following as {target} to be spoken aloud. Drop all code, file names, "
                   f"and how-it-works detail; keep only what changed, the result, and any question.")
    out = _ollama_chat(model, instruction, text)
    if out:
        return _strip_markup(out)

    # Fallback: strip markup and trim to a sane spoken length.
    clean = _strip_markup(text)
    sentences = re.split(r"(?<=[.!?])\s+", clean)
    n = 1 if mode == "headline" else 3
    return " ".join(sentences[:n]).strip()
