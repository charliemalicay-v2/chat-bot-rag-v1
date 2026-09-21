"""LLM provider layer.

`get_llm()` returns the provider chosen by settings.LLM_PROVIDER:
  ollama  local Ollama server (HTTP, streaming)
  fake    deterministic offline provider, used by tests and demos

Providers expose one method: stream_chat(messages) -> Iterator[str] of text
deltas. Any failure surfaces as LLMError so callers handle exactly one type.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator

import httpx
from django.conf import settings

logger = logging.getLogger(__name__)

Message = dict  # {"role": "system" | "user" | "assistant", "content": str}


class LLMError(Exception):
    """The model could not be reached or returned an error."""


def normalize_host(host: str) -> str:
    host = host.strip().rstrip("/")
    return host if "://" in host else f"http://{host}"


class OllamaProvider:
    def __init__(self, host: str | None = None, model: str | None = None, transport=None):
        self.base_url = normalize_host(host or settings.OLLAMA_HOST)
        self.model = model or settings.OLLAMA_MODEL
        self._transport = transport  # injectable for tests
        self._timeout = httpx.Timeout(connect=5.0, read=300.0, write=30.0, pool=5.0)

    def stream_chat(self, messages: list[Message]) -> Iterator[str]:
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "keep_alive": "30m",
            "options": {
                "temperature": settings.OLLAMA_TEMPERATURE,
                "num_ctx": settings.OLLAMA_NUM_CTX,
            },
        }
        try:
            with httpx.Client(timeout=self._timeout, transport=self._transport) as client:
                with client.stream("POST", f"{self.base_url}/api/chat", json=payload) as resp:
                    if resp.status_code != 200:
                        resp.read()
                        raise LLMError(self._error_text(resp))
                    for line in resp.iter_lines():
                        if not line:
                            continue
                        try:
                            obj = json.loads(line)
                        except json.JSONDecodeError as exc:
                            raise LLMError(f"Malformed response from Ollama: {line[:200]!r}") from exc
                        if obj.get("error"):
                            raise LLMError(str(obj["error"]))
                        text = obj.get("message", {}).get("content", "")
                        if text:
                            yield text
                        if obj.get("done"):
                            return
        except httpx.HTTPError as exc:
            raise LLMError(f"Could not reach Ollama at {self.base_url}: {exc}") from exc

    @staticmethod
    def _error_text(resp: httpx.Response) -> str:
        try:
            return str(resp.json().get("error") or resp.text)
        except ValueError:
            return resp.text or f"HTTP {resp.status_code}"


class FakeProvider:
    """Offline stand-in. Echoes the last user message so tests can assert on it.

    Every call is recorded in `calls` (the full message list), letting tests
    check what prompt/context the pipeline assembled.
    """

    def __init__(self, reply: str | None = None, fail_after: int | None = None):
        self.reply = reply
        self.fail_after = fail_after  # raise LLMError after N tokens (tests)
        self.calls: list[list[Message]] = []

    def stream_chat(self, messages: list[Message]) -> Iterator[str]:
        self.calls.append(messages)
        question = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        text = self.reply if self.reply is not None else f"[fake] You asked: {question}"
        if not text:
            return
        for i, word in enumerate(text.split(" ")):
            if self.fail_after is not None and i >= self.fail_after:
                raise LLMError("fake provider failure")
            yield word if i == 0 else f" {word}"


def get_llm():
    provider = settings.LLM_PROVIDER
    if provider == "ollama":
        return OllamaProvider()
    if provider == "fake":
        return FakeProvider()
    raise LLMError(f"Unknown LLM_PROVIDER {provider!r} (expected 'ollama' or 'fake')")
