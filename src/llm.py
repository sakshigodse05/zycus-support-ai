"""Thin wrapper around the LLM providers.

We call the HTTP endpoints directly with `requests` rather than pulling in a
vendor SDK. This keeps the dependency tree tiny, makes `pip install` reliable on
any machine, and lets us swap providers with a single env var (LLM_PROVIDER).

Two production concerns are handled here rather than in the callers:
  * Determinism — enforced by an on-disk response cache (see below).
  * Rate limits — exponential backoff on HTTP 429.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from pathlib import Path

import requests

from src.config import (
    LLM_PROVIDER, GEMINI_API_KEY, GEMINI_MODEL,
    GROQ_API_KEY, GROQ_MODEL, TEMPERATURE, MAX_OUTPUT_TOKENS,
)

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
REQUEST_TIMEOUT_S = 60
MAX_RETRIES_429 = 4

# On-disk response cache.
#
# Determinism (a hard Task 2 requirement) cannot be fully guaranteed by
# temperature=0 and a seed alone: providers batch requests across GPUs and the
# reduction order of floating-point operations varies between runs, so sampling
# can differ at the margins. We therefore enforce determinism by construction —
# an identical (provider, model, temperature, prompt) tuple always returns the
# stored response. It also makes repeated eval runs free and rate-limit-proof.
#
# Set LLM_CACHE=0 in the environment to bypass the cache (e.g. to measure true
# cold-start latency).
CACHE_DIR = Path(__file__).resolve().parent.parent / ".cache" / "llm"
CACHE_ENABLED = os.getenv("LLM_CACHE", "1") != "0"


class LLMError(Exception):
    """Raised when the model cannot be reached or returns unusable output."""


# --------------------------------------------------------------------------- #
# Cache
# --------------------------------------------------------------------------- #

def _cache_key(prompt: str, temperature: float) -> str:
    payload = f"{LLM_PROVIDER}|{GROQ_MODEL}|{GEMINI_MODEL}|{temperature}|{prompt}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _cache_get(key: str) -> str | None:
    if not CACHE_ENABLED:
        return None
    path = CACHE_DIR / f"{key}.txt"
    return path.read_text(encoding="utf-8") if path.exists() else None


def _cache_put(key: str, value: str) -> None:
    if not CACHE_ENABLED:
        return
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    (CACHE_DIR / f"{key}.txt").write_text(value, encoding="utf-8")


# --------------------------------------------------------------------------- #
# Providers
# --------------------------------------------------------------------------- #

def _call_gemini(prompt: str, temperature: float) -> str:
    if not GEMINI_API_KEY:
        raise LLMError("GEMINI_API_KEY is not set. See .env.example.")
    r = requests.post(
        GEMINI_URL.format(model=GEMINI_MODEL),
        headers={"x-goog-api-key": GEMINI_API_KEY, "Content-Type": "application/json"},
        json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": MAX_OUTPUT_TOKENS,
            },
        },
        timeout=REQUEST_TIMEOUT_S,
    )
    if r.status_code != 200:
        raise LLMError(f"Gemini HTTP {r.status_code}: {r.text[:300]}")
    return r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()


def _call_groq(prompt: str, temperature: float) -> str:
    if not GROQ_API_KEY:
        raise LLMError("GROQ_API_KEY is not set. See .env.example.")
    r = requests.post(
        GROQ_URL,
        headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
        json={
            "model": GROQ_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": MAX_OUTPUT_TOKENS,
            "seed": 42,  # determinism (Task 2 requirement)
        },
        timeout=REQUEST_TIMEOUT_S,
    )
    if r.status_code != 200:
        raise LLMError(f"Groq HTTP {r.status_code}: {r.text[:300]}")
    return r.json()["choices"][0]["message"]["content"].strip()


_PROVIDERS = {"gemini": _call_gemini, "groq": _call_groq}


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #

def ask_llm(prompt: str, temperature: float = TEMPERATURE) -> str:
    """Send a prompt to the configured provider, get raw text back.

    Cached by prompt hash (determinism), and retried with exponential backoff on
    HTTP 429 (free-tier rate limits).
    """
    call = _PROVIDERS.get(LLM_PROVIDER)
    if call is None:
        raise LLMError(f"Unknown LLM_PROVIDER '{LLM_PROVIDER}'. Use 'gemini' or 'groq'.")

    key = _cache_key(prompt, temperature)
    cached = _cache_get(key)
    if cached is not None:
        return cached

    delay = 8.0
    for attempt in range(MAX_RETRIES_429 + 1):
        try:
            result = call(prompt, temperature)
            _cache_put(key, result)
            return result
        except LLMError as exc:
            if "429" in str(exc) and attempt < MAX_RETRIES_429:
                time.sleep(delay)
                delay *= 1.5
                continue
            raise
        except requests.RequestException as exc:
            raise LLMError(f"Network error calling {LLM_PROVIDER}: {exc}") from exc

    raise LLMError("Exhausted retries against the provider rate limit.")


def _extract_json(text: str) -> str:
    """Strip ```json fences and grab the outermost {...} block."""
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise LLMError(f"No JSON object found in model output: {text[:200]}")
    return text[start:end + 1]


def ask_llm_json(prompt: str, temperature: float = TEMPERATURE, retries: int = 2) -> dict:
    """Send a prompt, get a validated Python dict back. Retries on malformed JSON."""
    last_error = None
    for _ in range(retries + 1):
        raw = ask_llm(prompt, temperature=temperature)
        try:
            return json.loads(_extract_json(raw))
        except (json.JSONDecodeError, LLMError) as exc:
            last_error = exc
            prompt += "\n\nYour previous reply was not valid JSON. Reply with ONLY a valid JSON object."
    raise LLMError(f"Model failed to produce valid JSON after {retries + 1} attempts: {last_error}")