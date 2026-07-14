"""Thin wrapper around the LLM providers.

We call the HTTP endpoints directly with `requests` rather than pulling in a
vendor SDK. This keeps the dependency tree tiny, makes `pip install` reliable,
and lets us swap providers with a single env var (LLM_PROVIDER).
"""
import json
import re
import requests

from src.config import (
    LLM_PROVIDER, GEMINI_API_KEY, GEMINI_MODEL,
    GROQ_API_KEY, GROQ_MODEL, TEMPERATURE, MAX_OUTPUT_TOKENS,
)

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
REQUEST_TIMEOUT_S = 60


class LLMError(Exception):
    """Raised when the model cannot be reached or returns unusable output."""


def _call_gemini(prompt: str, temperature: float) -> str:
    if not GEMINI_API_KEY:
        raise LLMError("GEMINI_API_KEY is not set. See .env.example.")
    r = requests.post(
        GEMINI_URL.format(model=GEMINI_MODEL),
        headers={"x-goog-api-key": GEMINI_API_KEY, "Content-Type": "application/json"},
        json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": temperature, "maxOutputTokens": MAX_OUTPUT_TOKENS},
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


def ask_llm(prompt: str, temperature: float = TEMPERATURE) -> str:
    """Send a prompt to the configured provider, get raw text back."""
    call = _PROVIDERS.get(LLM_PROVIDER)
    if call is None:
        raise LLMError(f"Unknown LLM_PROVIDER '{LLM_PROVIDER}'. Use 'gemini' or 'groq'.")
    try:
        return call(prompt, temperature)
    except requests.RequestException as exc:
        raise LLMError(f"Network error calling {LLM_PROVIDER}: {exc}") from exc


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