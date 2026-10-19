"""Pluggable LLM clients. Every client implements one method:

    complete(system, messages, tools, agent=None) -> {"stop_reason", "content": [blocks], "usage"}

Messages and content blocks use the Anthropic Messages API shape (text, tool_use, tool_result),
so the live client is a thin pass-through and the mock speaks the same protocol.

    make_client("live")   Claude API; key from ANTHROPIC_API_KEY, model from LABSYNC_MODEL
    make_client("mock")   deterministic offline agent (labsync_app.mock_llm)
"""
import json
import os
import time
import urllib.error
import urllib.request

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"
DEFAULT_MODEL = "claude-sonnet-5-5"


class LLMUnavailable(RuntimeError):
    """The live model can't be reached or isn't configured; callers fall back or report it."""


def _urllib_transport(url, headers, body, timeout):
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


class AnthropicClient:
    """Claude Messages API over the standard library. `transport` is injectable for tests."""

    name = "live"

    def __init__(self, api_key=None, model=None, max_tokens=4096, timeout=90, retries=2, transport=None):
        self.api_key = api_key if api_key is not None else os.environ.get("ANTHROPIC_API_KEY", "")
        self.model = model or os.environ.get("LABSYNC_MODEL") or DEFAULT_MODEL
        self.max_tokens = max_tokens
        self.timeout = timeout
        self.retries = retries
        self.transport = transport or _urllib_transport
        if not self.api_key:
            raise LLMUnavailable("ANTHROPIC_API_KEY is not set; use mock mode or set the key")

    def complete(self, system, messages, tools, agent=None):
        body = {"model": self.model, "max_tokens": self.max_tokens, "system": system, "messages": messages}
        if tools:
            body["tools"] = tools
        headers = {"x-api-key": self.api_key, "anthropic-version": API_VERSION, "content-type": "application/json"}
        payload = json.dumps(body).encode("utf-8")
        last = None
        for attempt in range(self.retries + 1):
            try:
                status, raw = self.transport(API_URL, headers, payload, self.timeout)
            except (urllib.error.URLError, OSError) as exc:
                status, raw, last = None, b"", str(exc)
            if status == 200:
                data = json.loads(raw)
                return {"stop_reason": data.get("stop_reason"), "content": data.get("content", []),
                        "usage": data.get("usage", {}), "model": data.get("model", self.model)}
            if status is not None:
                last = "HTTP %s: %s" % (status, raw[:300].decode("utf-8", "replace"))
                if status not in (408, 429, 500, 502, 503, 529):
                    break
            if attempt < self.retries:
                time.sleep(2 ** attempt)
        raise LLMUnavailable("Claude API call failed: %s" % last)


def make_client(mode="mock", **kwargs):
    if mode == "live":
        return AnthropicClient(**kwargs)
    if mode == "mock":
        from .mock_llm import MockClient
        return MockClient()
    raise ValueError("mode must be 'live' or 'mock'")
