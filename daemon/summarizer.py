"""Turn raw text (Claude Code output, notifications, selected text) into speech-ready prose.

The core of "don't read everything." Modes:
  verbatim  — clean markup so it reads naturally; still redacts secrets. No LLM.
  summary   — LLM condenses to the few things a human would want to HEAR (default).
  headline  — LLM reduces to a single spoken sentence.

Security/trust invariant: secrets, keys, tokens and file paths are REDACTED deterministically BEFORE
the text ever reaches the model, and code is replaced with a neutral marker so the model cannot read
or narrate it. We never rely on the model to "remember not to" — the redaction is hard code, applied
on the way in AND on the way out. Uses local Ollama if reachable; deterministic fallback otherwise.
"""
from __future__ import annotations

import hashlib
import json
import re
import urllib.request
from typing import Optional

OLLAMA_CHAT_URL = "http://127.0.0.1:11434/api/chat"

SYSTEM = (
    "You convert developer-tool and AI-assistant output into a brief SPOKEN update for a software "
    "engineer who is listening hands-free, not looking at the screen. Say only what a person would "
    "want to HEAR: decisions made, results, what changed, errors, blocking questions, and the next "
    "step. NEVER read code, file contents, diffs, logs, stack traces, URLs, file paths, or anything "
    "marked [redacted]. No markdown, no symbols, no bullet points, no emoji. Expand abbreviations into "
    "spoken words. Use plain natural sentences. Be concise. Output ONLY the spoken text itself — no "
    "preamble, no labels, no quotation marks, no commentary."
)

# One-shot example as a real user/assistant turn so small instruct models copy the FORMAT.
EX_IN = ("I'll add the limiter. (a code change) Wired it in and added 4 tests. Ran the suite: 18 "
         "passed, 1 failed on the burst test, off by one at the window boundary. Fix it or loosen the test?")
EX_OUT = ("Added the rate limiter and four tests. Eighteen passed, but the burst test failed on an "
          "off-by-one at the window boundary. Want me to fix the boundary or loosen the test?")

_PREAMBLE = re.compile(
    r"^\s*(here(?:'s| is| are)[^:]*:|spoken( output)?:|sure[,!.]?|okay[,!.]?|output:)\s*",
    re.IGNORECASE)

# --- hard redaction (applied in AND out) ------------------------------------------------------
_SECRET_PATTERNS = [
    re.compile(r"\b(?:sk|pk|rk|sk-proj|sk-ant)-[A-Za-z0-9_\-]{6,}", re.I),     # openai/anthropic-style
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{16,}\b"),                              # github tokens
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),                                        # aws access key id
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),                            # slack
    re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]+\b"),  # jwt
    re.compile(r"-----BEGIN[^-]+PRIVATE KEY-----.*?-----END[^-]+PRIVATE KEY-----", re.S),
    # "secret = value", "api_key: value", "password=..."
    re.compile(r"(?i)\b(api[_-]?key|secret|secret[_-]?key|token|access[_-]?token|password|passwd|pwd|"
               r"client[_-]?secret|auth(?:orization)?|bearer)\b\s*[:=]\s*[\"']?[^\s\"',;]{4,}"),
    re.compile(r"\b[A-Fa-f0-9]{40,}\b"),                                        # long hex (hashes/keys)
]
_PATH_PATTERNS = [
    re.compile(r"\b[\w./~@-]*\.(?:py|ts|tsx|js|jsx|go|rs|rb|java|kt|swift|c|cc|cpp|h|hpp|cs|php|"
               r"json|ya?ml|toml|env|sh|bash|zsh|sql|md|txt|cfg|ini|lock|xml|html|css|scss)\b"),
    re.compile(r"(?:/[\w.\-]+){2,}/?"),                                         # absolute-ish paths
]


def _redact(text: str) -> str:
    for p in _SECRET_PATTERNS:
        text = p.sub("[redacted]", text)
    for p in _PATH_PATTERNS:
        text = p.sub("a file", text)
    text = re.sub(r"(?:a file[ ,]*){2,}", "a file ", text)   # collapse repeats
    return text


def _strip_markup(text: str) -> str:
    text = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)          # fenced code -> drop
    text = re.sub(r"\(\s*(?:a\s+)?code(?:\s+change)?\s*\)", "", text, flags=re.IGNORECASE)
    text = re.sub(r"`[^`]+`", "", text)                              # inline code
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)                 # images
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)             # links -> label
    text = re.sub(r"https?://\S+", "", text)                         # bare urls
    text = re.sub(r"^[#>\-\*\+\s]+", "", text, flags=re.MULTILINE)   # md line prefixes
    text = re.sub(r"[*_#`>|]", "", text)                             # stray md symbols
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{2,}", ". ", text).replace("\n", " ")
    return text.strip()


def _for_llm(text: str) -> str:
    """What the model is allowed to see: code neutralized, secrets/paths redacted."""
    had_code = bool(re.search(r"```", text))
    text = re.sub(r"```.*?```", " (a code change) ", text, flags=re.DOTALL)
    text = re.sub(r"`[^`]+`", " ", text)
    text = _redact(text)
    return text, had_code


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


_LABEL_CACHE = {}


def to_label(context: str, model: str = "llama3.2:3b") -> str:
    """A short 2-4 word label for what a terminal session is working on, from its recent context.
    Cached by context so repeated notifications in the same session don't re-ask the model."""
    context = _redact((context or "").strip())
    if len(context) < 8:
        return ""
    key = hashlib.md5(context.encode()).hexdigest()
    if key in _LABEL_CACHE:
        return _LABEL_CACHE[key]
    body = json.dumps({
        "model": model, "stream": False,
        "messages": [
            {"role": "system", "content": "Name what a coding session is about with a 2 to 4 word "
             "lowercase noun phrase. No leading 'to', no leading verb, no punctuation, no markdown, "
             "no preamble. Just the phrase."},
            {"role": "user", "content": "fix the failing login tests"},
            {"role": "assistant", "content": "login test fixes"},
            {"role": "user", "content": "redesign the landing page hero with a bolder headline"},
            {"role": "assistant", "content": "landing page redesign"},
            {"role": "user", "content": context[:1500]},
        ],
        "options": {"temperature": 0.1, "num_predict": 12},
    }).encode()
    label = ""
    try:
        req = urllib.request.Request(OLLAMA_CHAT_URL, data=body,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as r:
            out = json.loads(r.read()).get("message", {}).get("content", "").strip()
        out = re.sub(r"[*_`\"#.]", "", out).strip().lower()
        out = re.sub(r"^(this |the |a |an )?(session |work |task )?(is )?(about|on|for|to)\s+", "", out)
        label = " ".join(out.split()[:4])
    except Exception:
        label = ""
    _LABEL_CACHE[key] = label
    return label


def to_speech(text: str, mode: str = "summary", model: str = "llama3.2:3b") -> str:
    text = (text or "").strip()
    if not text:
        return ""
    if mode == "verbatim":
        return _redact(_strip_markup(_redact(text)))

    llm_input, had_code = _for_llm(text)
    # how much human prose is there once code/markup/secrets are gone?
    prose = _strip_markup(llm_input)
    if len(prose.split()) < 4:
        # essentially just code / a secret / a path — never narrate it
        return "Made some code changes." if had_code else (prose or "Done.")

    target = "a single short sentence" if mode == "headline" else "at most two or three sentences"
    instruction = (f"Rewrite the following as {target} to be spoken aloud. Drop all code, file names, "
                   f"and how-it-works detail; keep only what changed, the result, and any question.")
    out = _ollama_chat(model, instruction, llm_input)
    if out:
        return _redact(_strip_markup(out))    # belt-and-suspenders redact on the way out too

    # Fallback: trimmed prose (already code-stripped + redacted).
    sentences = re.split(r"(?<=[.!?])\s+", prose)
    n = 1 if mode == "headline" else 3
    return _redact(" ".join(sentences[:n]).strip())
