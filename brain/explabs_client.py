"""Experiential Labs OpenAI-compatible Chat Completions adapter.

Explicit opt-in only. Never shares Anthropic/Codex credentials or silently
falls back to a different provider. Do not log auth headers or response bodies
on errors. Gateway usage.cost is already in USD.
"""
from __future__ import annotations

import math
import os
import re
from urllib.parse import urlsplit
from dataclasses import dataclass
from typing import Any

import httpx

BASE_URL = "https://api.experientiallabs.ai/v1"


def validated_shared_gateway_origin(value: str) -> str:
    """Accept only explicit numeric local IPv4 tunnel targets for scoped tokens.

    Never DNS resolve localhost or accept a remote endpoint. A gateway on a
    remote host must be reached by an authorized local loopback tunnel.
    """
    if not isinstance(value, str) or value != value.strip():
        raise ExperientialError("explabs_invalid_gateway_origin")
    if any(ord(ch) < 33 or ord(ch) > 126 for ch in value):
        raise ExperientialError("explabs_invalid_gateway_origin")
    try:
        parts = urlsplit(value)
        port = parts.port
        valid = (
            parts.scheme in {"http", "https"}
            and parts.hostname == "127.0.0.1"
            and parts.netloc == f"127.0.0.1:{port}"
            and port is not None and 1 <= port <= 65535
            and not parts.path and not parts.query and not parts.fragment
            and parts.username is None and parts.password is None
            and value == f"{parts.scheme}://127.0.0.1:{port}"
        )
    except ValueError:
        valid = False
    if not valid:
        raise ExperientialError("explabs_invalid_gateway_origin")
    return value
DEFAULT_MODEL = "deepseek-v4.1-flash"


class ExperientialError(RuntimeError):
    """Sanitized, credential-free gateway failure and typed admission outcome."""

    def __init__(
        self,
        reason: str,
        *,
        status: int | None = None,
        code: str | None = None,
        retry_after: int | None = None,
    ) -> None:
        super().__init__(reason)
        self.status = status
        self.code = code
        self.retry_after = retry_after


@dataclass(frozen=True)
class Completion:
    text: str | None
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float | None
    provider: str | None
    is_byok: bool | None
    request_id: str | None
    account_slot: str | None = None


def available() -> bool:
    return bool(os.environ.get("EXPLABS_API_KEY"))


def chat_completion(
    messages: list[dict[str, str]],
    *,
    model: str | None = None,
    client: httpx.Client | None = None,
    api_key: str | None = None,
    max_tokens: int | None = None,
    shared_gateway_origin: str | None = None,
) -> httpx.Response:
    """Send model + messages, optionally with a bounded output-token cap.

    Injecting an httpx Client allows fully offline tests. The production base
    URL is fixed to avoid leaking the gateway key to an accidental override.
    """
    key = api_key if api_key is not None else os.environ.get("EXPLABS_API_KEY")
    if not key:
        raise ExperientialError("explabs_missing_key")
    if shared_gateway_origin is None:
        if (os.environ.get("EXPLABS_BASE_URL") or BASE_URL).rstrip("/") != BASE_URL:
            raise ExperientialError("explabs_invalid_base_url")
        target = BASE_URL
    else:
        # Explicitly bound by the account selector, not an arbitrary env override.
        target = validated_shared_gateway_origin(shared_gateway_origin) + "/v1"
    selected_model = model or os.environ.get("EXPLABS_MODEL") or DEFAULT_MODEL
    if not isinstance(selected_model, str) or not selected_model.strip():
        raise ExperientialError("explabs_invalid_model")
    body = {"model": selected_model, "messages": messages}
    if max_tokens is not None:
        if type(max_tokens) is not int or not 1 <= max_tokens <= 32768:
            raise ExperientialError("explabs_invalid_max_tokens")
        # The gateway enforces the daily key spend cap against worst-case
        # output budget, not only the tokens actually generated. The minimal
        # catalog/smoke wire call keeps its two-field body by default.
        body["max_tokens"] = max_tokens
    post = client.post if client is not None else httpx.post
    # A scoped local token must never follow ambient HTTP_PROXY/ALL_PROXY
    # configuration into a non-loopback intermediary. Explicitly injected
    # test clients own their own transport; production top-level calls must
    # use direct loopback sockets.
    transport_policy = (
        {"trust_env": False}
        if shared_gateway_origin is not None and client is None else {}
    )
    try:
        response = post(
            f"{target}/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json=body,
            timeout=30.0,
            **transport_policy,
        )
    except httpx.HTTPError:
        raise ExperientialError("explabs_transport_error") from None
    if 300 <= response.status_code < 400:
        raise ExperientialError(
            "explabs_upstream_redirect_refused", status=response.status_code,
        )
    if response.status_code >= 400:
        # Branch on the documented machine code, never raw provider prose.
        try:
            envelope = response.json().get("error") or {}
            code = envelope.get("code") if isinstance(envelope, dict) else None
        except (ValueError, AttributeError):
            code = None
        if not isinstance(code, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", code):
            code = "unknown"
        raw_retry = response.headers.get("retry-after")
        retry_after = int(raw_retry) if raw_retry and raw_retry.isdecimal() else None
        raise ExperientialError(
            f"explabs_http_{response.status_code}:{code}",
            status=response.status_code,
            code=code,
            retry_after=min(retry_after, 3600) if retry_after is not None else None,
        )
    return response


def complete(
    system: str,
    user: str,
    *,
    model: str | None = None,
    client: httpx.Client | None = None,
    api_key: str | None = None,
    max_tokens: int | None = None,
    shared_gateway_origin: str | None = None,
) -> Completion:
    """Return text and gateway-reported usage, without changing sampling."""
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": user})
    response = chat_completion(
        messages, model=model, client=client, api_key=api_key,
        max_tokens=max_tokens, shared_gateway_origin=shared_gateway_origin,
    )
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
        if cost is not None and (not math.isfinite(cost) or cost < 0):
            raise ValueError("invalid_gateway_cost")
        provider = data.get("provider") or response.headers.get("x-gateway-provider")
        raw_lane = usage.get("is_byok")
        if not isinstance(raw_lane, bool):
            raw_lane = data.get("is_byok")
        is_byok = raw_lane if isinstance(raw_lane, bool) else None
        return Completion(
            text=content,
            model=str(data.get("model") or model or os.environ.get("EXPLABS_MODEL") or DEFAULT_MODEL),
            input_tokens=int(usage.get("prompt_tokens") or 0),
            output_tokens=int(usage.get("completion_tokens") or 0),
            cost_usd=cost,
            provider=str(provider) if provider else None,
            is_byok=is_byok,
            request_id=response.headers.get("x-request-id"),
        )
    except (KeyError, IndexError, TypeError, ValueError):
        raise ExperientialError("explabs_invalid_response") from None
