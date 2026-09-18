"""Shared wire-protocol vocabulary for subscription plans and harness bindings.

One owner for the names a purchased plan and a reviewed binding may share.
`openai-compatible` is retired; OpenAI-family plans use `openai-chat` or
`responses`.
"""
from __future__ import annotations

from typing import Any

PROVIDER_PROTOCOLS = frozenset({"anthropic", "openai-chat", "responses"})


class ProviderProtocolError(ValueError):
    """A wire-protocol name is missing from the shared vocabulary."""


def validate_provider_protocol(value: Any) -> str:
    if not isinstance(value, str) or value not in PROVIDER_PROTOCOLS:
        raise ProviderProtocolError(f"unsupported provider protocol: {value!r}")
    return value


__all__ = [
    "PROVIDER_PROTOCOLS",
    "ProviderProtocolError",
    "validate_provider_protocol",
]
