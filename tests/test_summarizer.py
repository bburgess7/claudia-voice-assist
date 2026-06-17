"""Security/trust tests for the spoken summarizer.

The invariant that matters most: Claudia must NEVER speak secrets, keys, tokens, file paths, or raw
code aloud. These tests assert the deterministic redaction holds WITHOUT a model running (they patch
the LLM call to None so only the hard-coded redaction + fallback path is exercised — deterministic
and CI-safe).

Run:  .venv/bin/python -m pytest tests/ -q     (or: .venv/bin/python tests/test_summarizer.py)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from daemon import summarizer as s

# force the deterministic (no-LLM) path so tests don't depend on Ollama
s._ollama_chat = lambda *a, **k: None

FORBIDDEN = [
    "sk-abc123xyz", "sk-proj-9f8a7b6c5d4e", "ghp_0123456789abcdef0123",
    "AKIA1234567890ABCDEF", "hunter2supersecret", "SECRET_TOKEN",
    "class Bar", "def foo", "return 42",
    "config.py", "send.py", "/Users/ben/secret",
]

CASES = [
    "API_KEY=sk-abc123xyz and OPENAI_API_KEY = sk-proj-9f8a7b6c5d4e. Deploying.",
    "password=hunter2supersecret and AWS key AKIA1234567890ABCDEF. Restarted.",
    "github token ghp_0123456789abcdef0123 committed by mistake, rotating now.",
    "```python\nclass Bar:\n    def foo(self):\n        return 42\n```",
    "Refactored auth.\n```ts\nexport const t = process.env.SECRET_TOKEN\n```\nRan tests/auth.spec.ts, 18 passed.",
    "Edited /Users/ben/secret/config.py and src/api/send.py, all green.",
]


def test_no_secret_or_code_leaks():
    for raw in CASES:
        for mode in ("summary", "headline", "verbatim"):
            out = s.to_speech(raw, mode=mode).lower()
            for bad in FORBIDDEN:
                assert bad.lower() not in out, f"LEAKED {bad!r} in {mode}: {out!r}"


def test_pure_code_is_not_narrated():
    out = s.to_speech("```python\nclass Bar:\n    def foo(self): return 42\n```", mode="summary")
    assert "code" in out.lower() and "foo" not in out.lower()


def test_keeps_the_gist():
    out = s.to_speech("Refactored the auth handler. 18 tests passed, 1 failed on expiry. Fix it?",
                      mode="summary").lower()
    assert "fail" in out or "expiry" in out or "fix" in out


if __name__ == "__main__":
    test_no_secret_or_code_leaks()
    test_pure_code_is_not_narrated()
    test_keeps_the_gist()
    print("ok — all summarizer security tests passed")
