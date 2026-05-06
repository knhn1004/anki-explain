"""OpenRouter chat completions client.

Pure I/O — no Qt imports. Streaming via SSE parser yielding text deltas.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Iterator

import urllib.error
import urllib.request

API_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_HEADERS_REFERER = "https://github.com/oliver/anki-explain"
DEFAULT_HEADERS_TITLE = "anki-explain"


class OpenRouterError(RuntimeError):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


@dataclass
class ChatRequest:
    model: str
    messages: list[dict]
    web_search: bool = True
    web_search_max_results: int = 5
    extra_tools: list[dict] = field(default_factory=list)

    def to_body(self, stream: bool) -> dict:
        body: dict = {
            "model": self.model,
            "messages": self.messages,
            "stream": stream,
        }
        if self.extra_tools:
            body["tools"] = list(self.extra_tools)
        if self.web_search:
            body["plugins"] = [{
                "id": "web",
                "max_results": self.web_search_max_results,
            }]
        return body


def _headers(api_key: str) -> dict:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": DEFAULT_HEADERS_REFERER,
        "X-Title": DEFAULT_HEADERS_TITLE,
    }


def complete(req: ChatRequest, api_key: str, timeout: float = 60.0) -> str:
    """Non-streaming completion. Returns assistant text."""
    body = json.dumps(req.to_body(stream=False)).encode("utf-8")
    request = urllib.request.Request(API_URL, data=body, headers=_headers(api_key), method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise OpenRouterError(_format_http_error(e), status=e.code) from e
    except urllib.error.URLError as e:
        raise OpenRouterError(f"network error: {e.reason}") from e
    return _extract_message(data)


def stream(req: ChatRequest, api_key: str, timeout: float = 120.0) -> Iterator[str]:
    """Streaming completion. Yields text deltas as they arrive."""
    body = json.dumps(req.to_body(stream=True)).encode("utf-8")
    headers = _headers(api_key)
    headers["Accept"] = "text/event-stream"
    request = urllib.request.Request(API_URL, data=body, headers=headers, method="POST")
    try:
        resp = urllib.request.urlopen(request, timeout=timeout)
    except urllib.error.HTTPError as e:
        raise OpenRouterError(_format_http_error(e), status=e.code) from e
    except urllib.error.URLError as e:
        raise OpenRouterError(f"network error: {e.reason}") from e

    with resp:
        for delta in _parse_sse(resp):
            yield delta


def _parse_sse(resp) -> Iterator[str]:
    buffer = b""
    while True:
        chunk = resp.read1(4096) if hasattr(resp, "read1") else resp.read(4096)
        if not chunk:
            break
        buffer += chunk
        while b"\n" in buffer:
            line, buffer = buffer.split(b"\n", 1)
            line = line.strip()
            if not line or line.startswith(b":"):
                continue
            if not line.startswith(b"data:"):
                continue
            payload = line[5:].strip()
            if payload == b"[DONE]":
                return
            try:
                event = json.loads(payload)
            except json.JSONDecodeError:
                continue
            choices = event.get("choices") or []
            if not choices:
                continue
            delta = choices[0].get("delta") or {}
            content = delta.get("content")
            if content:
                yield content


def _extract_message(data: dict) -> str:
    choices = data.get("choices") or []
    if not choices:
        return ""
    msg = choices[0].get("message") or {}
    return msg.get("content") or ""


def _format_http_error(err: urllib.error.HTTPError) -> str:
    try:
        body = err.read().decode("utf-8")
    except Exception:
        return f"HTTP {err.code}: {err}"
    try:
        parsed = json.loads(body)
        e = parsed.get("error", {}) if isinstance(parsed, dict) else {}
        message = e.get("message") or body
        meta = e.get("metadata") or {}
        # OpenRouter often nests provider-side info under metadata.raw / .provider_name
        if meta:
            message = f"{message} | metadata={json.dumps(meta)[:600]}"
    except Exception:
        message = body[:1000]
    return f"HTTP {err.code}: {message}"
