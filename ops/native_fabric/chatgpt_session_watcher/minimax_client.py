"""MiniMax client for the fabric minimax pool.

The key is read from the same ~/.minimax/config.json the fabric lane uses.
It is never placed on argv, never logged, and never copied into an exception.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

from registration import MODEL, POOL

DEFAULT_URL = "https://api.minimax.io/v1/chat/completions"
_UNAVAILABLE = "minimax pool request failed"


class MinimaxUnavailable(Exception):
    pass


class MinimaxPoolClient:
    pool = POOL
    model = MODEL

    def __init__(self, transport=None, config_path: Path | None = None, url: str = DEFAULT_URL, model: str | None = None):
        self._transport = transport or _urllib_transport
        self.config_path = config_path or Path.home() / ".minimax" / "config.json"
        self.url = url
        env_model = os.environ.get("MMX_MINIMAX_MODEL")
        self.model = model or env_model or MODEL

    def _key(self) -> str:
        try:
            raw = json.loads(self.config_path.read_text(encoding="utf-8"))
            key = raw.get("api_key") or raw.get("apiKey")
        except (OSError, json.JSONDecodeError, AttributeError):
            raise MinimaxUnavailable(_UNAVAILABLE) from None
        if not isinstance(key, str) or not key.strip():
            raise MinimaxUnavailable(_UNAVAILABLE) from None
        return key

    def complete(self, messages: list[dict], *, max_tokens: int = 400, temperature: float = 0.2) -> str:
        key = self._key()
        body = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        headers = {"Authorization": "Bearer " + key, "Content-Type": "application/json"}
        try:
            payload = self._transport(self.url, headers, body)
        except MinimaxUnavailable:
            raise
        except Exception:
            raise MinimaxUnavailable(_UNAVAILABLE) from None
        text = _content(payload)
        if key and key in text:
            text = text.replace(key, "[redacted]")
        return text


def _content(payload: dict) -> str:
    try:
        content = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise MinimaxUnavailable(_UNAVAILABLE) from None
    if not isinstance(content, str) or not content.strip():
        raise MinimaxUnavailable(_UNAVAILABLE) from None
    return content.strip()


def _urllib_transport(url: str, headers: dict, body: dict) -> dict:
    data = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError, OSError):
        raise MinimaxUnavailable(_UNAVAILABLE) from None
