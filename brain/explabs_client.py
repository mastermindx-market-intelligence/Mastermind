"""Experiential Labs OpenAI-compatible Chat Completions adapter.

Explicit opt-in only. Never shares Anthropic/Codex credentials or silently
falls back to a different provider. Do not log auth headers or response bodies
on errors. Gateway usage.cost is already in USD.
"""
from __future__ import annotations

import ipaddress
import math
import os
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import httpx

BASE_URL = "https://api.experientiallabs.ai/v1"
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


def pinned_local_gateway_url(value: str) -> str:
    """Only one numeric loopback gateway v1 path, never a vendor hostname.

    The Brain client can be placed on another machine only by a separately
    approved encrypted tunnel that terminates on this worker's loopback.
    A hostname here would be re-resolved when HTTPX dials, so disallow it.
    """
    if not isinstance(value, str) or not value:
        raise ExperientialError("explabs_shared_gateway_required")
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
        port = parsed.port
        address = ipaddress.ip_address(hostname or "")
    except (ValueError, TypeError):
        raise ExperientialError("explabs_shared_gateway_invalid_url") from None
    if (parsed.scheme != "http" or not address.is_loopback or
            parsed.path != "/v1" or parsed.query or parsed.fragment or
            parsed.username or parsed.password or port is None or
            not 1024 <= port <= 65535):
        raise ExperientialError("explabs_shared_gateway_invalid_url")
    # Numeric IPv4 only for the first reviewed localhost deployment.
    # A verified IPv6/tunnel deployment needs a distinct owner-approved path.
    if address.version != 4 or hostname != "127.0.0.1":
        raise ExperientialError("explabs_shared_gateway_invalid_url")
    canonical = f"http://127.0.0.1:{port}/v1"
    if value != canonical:
        raise ExperientialError("explabs_shared_gateway_invalid_url")
    return canonical


def scoped_gateway_token(value: str) -> str:
    """Validate only the existing gateway's opaque local bearer capability."""
    if (not isinstance(value, str) or not 24 <= len(value) <= 512 or
            not value.isascii() or
            any(ord(ch) < 33 or ord(ch) > 126 for ch in value)):
        raise ExperientialError("explabs_shared_gateway_token_unavailable")
    return value


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
    shared_gateway_url: str | None = None,
    local_proxy_token: str | None = None,
) -> httpx.Response:
    """Send model + messages, optionally with a bounded output-token cap.

    Injecting an httpx Client allows fully offline tests. The production base
    URL is fixed to avoid leaking the gateway key to an accidental override.
    """
    if shared_gateway_url is not None or local_proxy_token is not None:
        # The pool must never send its upstream xpl_ key to a model request.
        endpoint = pinned_local_gateway_url(shared_gateway_url)
        key = scoped_gateway_token(local_proxy_token)
    else:
        if os.environ.get("EXPLABS_POOL_ENABLED") == "1":
            # A pool-selected Brain completion must share the same RPM owner
            # as Jev and Fabric. No direct provider fallback is permissible.
            raise ExperientialError("explabs_pool_requires_shared_gateway")
        key = api_key if api_key is not None else os.environ.get("EXPLABS_API_KEY")
        if not key:
            raise ExperientialError("explabs_missing_key")
        endpoint = BASE_URL
    if (os.environ.get("EXPLABS_BASE_URL") or BASE_URL).rstrip("/") != BASE_URL:
        raise ExperientialError("explabs_invalid_base_url")
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
    try:
        if client is not None:
            response = client.post(
                f"{endpoint}/chat/completions",
                headers={"Authorization": f"Bearer {key}"},
                json=body, timeout=30.0,
            )
        elif shared_gateway_url is not None:
            # Never allow an HTTP_PROXY/HTTPS_PROXY environment variable to
            # receive the local gateway capability. The caller's transport
            # is explicitly loopback and redirects are forbidden.
            with httpx.Client(trust_env=False, follow_redirects=False) as scoped:
                response = scoped.post(
                    f"{endpoint}/chat/completions",
                    headers={"Authorization": f"Bearer {key}"},
                    json=body, timeout=30.0,
                )
        else:
            response = httpx.post(
                f"{endpoint}/chat/completions",
                headers={"Authorization": f"Bearer {key}"},
                json=body, timeout=30.0,
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
    shared_gateway_url: str | None = None,
    local_proxy_token: str | None = None,
) -> Completion:
    """Return text and gateway-reported usage, without changing sampling."""
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": user})
    response = chat_completion(
        messages, model=model, client=client, api_key=api_key,
        max_tokens=max_tokens,
        shared_gateway_url=shared_gateway_url,
        local_proxy_token=local_proxy_token,
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
