"""OpenAI-compatible chat client (OpenRouter, Gemini's OpenAI endpoint, ...). No mock responses, no silent fallback:
any failure raises LlmError and is counted so the administrator console can report it."""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from typing import Any

import httpx


class LlmError(RuntimeError):
    """The LLM is not configured, unreachable, or returned something unusable."""


@dataclass
class LlmStats:
    requests: int = 0
    failures: int = 0
    last_error: str | None = None
    last_error_at: float | None = None
    last_ok_at: float | None = None
    last_latency_ms: int | None = None
    recent_errors: list[dict[str, Any]] = field(default_factory=list)


_lock = threading.Lock()
STATS = LlmStats()


def _fail(msg: str) -> LlmError:
    with _lock:
        STATS.failures += 1
        STATS.last_error, STATS.last_error_at = msg, time.time()
        STATS.recent_errors = ([{"at": time.time(), "error": msg}] + STATS.recent_errors)[:10]
    return LlmError(msg)


class LlmClient:
    def __init__(self, api_key: str | None, base_url: str | None, model: str | None, timeout: float = 90.0,
                 reasoning_effort: str | None = None):
        self.api_key, self.base_url, self.model, self.timeout = api_key, base_url, model, timeout
        self.reasoning_effort = reasoning_effort

    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.base_url and self.model)

    def missing(self) -> list[str]:
        return [n for n, v in (("LLM_API_KEY", self.api_key), ("LLM_BASE_URL", self.base_url),
                               ("LLM_MODEL", self.model)) if not v]

    def chat_json(self, system: str, user: str, temperature: float = 0.1,
                  history: list[dict[str, str]] | None = None) -> tuple[dict[str, Any], str]:
        """Return (parsed JSON object, raw text). `history` = earlier {role, content} turns. Raises LlmError."""
        if not self.configured:
            raise _fail(f"LLM is not configured; missing {', '.join(self.missing())}")
        body = {"model": self.model, "temperature": temperature,
                "response_format": {"type": "json_object"},
                "messages": [{"role": "system", "content": system}, *(history or []),
                             {"role": "user", "content": user}]}
        if self.reasoning_effort:
            body["reasoning_effort"] = self.reasoning_effort
        t0 = time.time()
        with _lock:
            STATS.requests += 1
        try:
            r = httpx.post(f"{self.base_url}/chat/completions", json=body, timeout=self.timeout,
                           headers={"Authorization": f"Bearer {self.api_key}"})
        except httpx.HTTPError as e:
            raise _fail(f"LLM request failed: {type(e).__name__}: {e}") from e
        if r.status_code != 200:
            raise _fail(f"LLM provider returned HTTP {r.status_code}: {r.text[:300]}")
        try:
            text = r.json()["choices"][0]["message"]["content"]
        except (KeyError, IndexError, ValueError) as e:
            raise _fail(f"LLM response had an unexpected shape: {r.text[:300]}") from e
        try:
            obj = json.loads(_strip_fence(text))
        except ValueError as e:
            raise _fail(f"LLM did not return valid JSON: {text[:300]}") from e
        if not isinstance(obj, dict):
            raise _fail("LLM JSON was not an object")
        with _lock:
            STATS.last_ok_at, STATS.last_latency_ms = time.time(), int((time.time() - t0) * 1000)
        return obj, text

    def ping(self) -> dict[str, Any]:
        """Live connectivity check: lists models with the configured key (does not spend generation tokens)."""
        if not self.configured:
            return {"connected": False, "error": f"missing {', '.join(self.missing())}"}
        t0 = time.time()
        try:
            r = httpx.get(f"{self.base_url}/models", timeout=15, headers={"Authorization": f"Bearer {self.api_key}"})
        except httpx.HTTPError as e:
            return {"connected": False, "error": f"{type(e).__name__}: {e}"}
        ms = int((time.time() - t0) * 1000)
        if r.status_code != 200:
            return {"connected": False, "error": f"HTTP {r.status_code}: {r.text[:200]}", "latency_ms": ms}
        return {"connected": True, "latency_ms": ms}


def _strip_fence(t: str) -> str:
    t = t.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t
        t = t.rsplit("```", 1)[0]
    return t
