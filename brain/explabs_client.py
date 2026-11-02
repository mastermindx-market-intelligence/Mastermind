"""Experiential Labs OpenAI-compatible Chat Completions adapter.

Explicit opt-in only. Never shares Anthropic/Codex credentials or silently
falls back to a different provider. Do not log auth headers or response bodies
on errors. Gateway usage.cost is already in USD.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any

import httpx

BASE_URL = "https://api.experientiallabs.ai/v1"
DEFAULT_MODEL = "deepseek-v4.1-flash"


class ExperientialError(RuntimeError):
    """Sanitized, credential-free gateway failure."""


@dataclass(frozen=True)
class Completion:
    text: str | None
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float | None
    provider: str | None
    is_byok: bool
    request_id: str | None


def available() -> bool:
    return bool(os.environ.get("EXPLABS_API_KEY"))


def chat_completion(
    messages: list[dict[str, str]],
    *,
    model: str | None = None,
    client: httpx.Client | None = None,
) -> httpx.Response:
    """Send exactly model + messages, with no sampling overrides.

    Injecting an httpx Client allows fully offline tests. The production base
    URL is fixed to avoid leaking the gateway key to an accidental override.
    """
    key = os.environ.get("EXPLABS_API_KEY")
    if not key:
        raise ExperientialError("explabs_missing_key")
    if (os.environ.get("EXPLABS_BASE_URL") or BASE_URL).rstrip("/") != BASE_URL:
        raise ExperientialError("explabs_invalid_base_url")
    selected_model = model or os.environ.get("EXPLABS_MODEL") or DEFAULT_MODEL
    if not isinstance(selected_model, str) or not selected_model.strip():
        raise ExperientialError("explabs_invalid_model")
    body = {"model": selected_model, "messages": messages}
    post = client.post if client is not None else httpx.post
    try:
        response = post(
            f"{BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json=body,
            timeout=30.0,
        )
    except httpx.HTTPError:
        raise ExperientialError("explabs_transport_error") from None
    if response.status_code >= 400:
        # Branch on the documented machine code, never raw provider prose.
        try:
            envelope = response.json().get("error") or {}
            code = envelope.get("code") if isinstance(envelope, dict) else None
        except (ValueError, AttributeError):
            code = None
        if not isinstance(code, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", code):
            code = "unknown"
        raise ExperientialError(f"explabs_http_{response.status_code}:{code}")
    return response


def complete(
    system: str,
    user: str,
    *,
    model: str | None = None,
    client: httpx.Client | None = None,
) -> Completion:
    """Return text and gateway-reported usage, without changing sampling."""
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": user})
    response = chat_completion(messages, model=model, client=client)
    try:
        data: dict[str, Any] = response.json()
        msg = data["choices"][0]["message"]
        content = msg.get("content")
        if not isinstance(content, str) and content is not None:
            raise ValueError("unsupported_content")
        usage = data.get("usage") or {}
        if not isinstance(usage, dict):
            raise ValueError("unsupported_usage")
        raw_cost = usage.get("cost")
        cost = float(raw_cost) if type(raw_cost) in (int, float) else None
        provider = data.get("provider") or response.headers.get("x-gateway-provider")
        return Completion(
            text=content,
            model=str(data.get("model") or model or os.environ.get("EXPLABS_MODEL") or DEFAULT_MODEL),
            input_tokens=int(usage.get("prompt_tokens") or 0),
            output_tokens=int(usage.get("completion_tokens") or 0),
            cost_usd=cost,
            provider=str(provider) if provider else None,
            is_byok=data.get("is_byok") is True or usage.get("is_byok") is True,
            request_id=response.headers.get("x-request-id"),
        )
    except (KeyError, IndexError, TypeError, ValueError):
        raise ExperientialError("explabs_invalid_response") from None
