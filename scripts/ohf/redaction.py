"""Secret redaction for OHF-P0 evidence.

Untrusted streams (stderr, harness errors, MCP errors, environment fixtures)
go through ``common.redaction.sanitize_external_text`` — the same sanitizer
pinned by ``tests/test_secret_redaction.py``.  That is the house subsystem;
this module does not invent a weaker one.

The finished probe document uses a tighter pass (exact env secrets, JWT, and
known credential prefixes) so SHA-256 attestation digests are not eaten by the
hex/token catch-alls.  ``bridge.nw_feedback._redact_secrets`` is not called: it
publishes a governance event and would violate laboratory inertness.
"""
from __future__ import annotations

import re
from typing import Any

from common.redaction import (
    REDACTION as REDACTED,
    environment_secrets,
    sanitize_external_text,
)
from common.redaction import _JWT_RE, _PREFIXED_SECRET_RE
from control_plane.flags import _SECRET_MARKERS

_EMAIL = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")
_MASTERMIND_ENV = re.compile(r"\bMASTERMIND_[A-Z_]+\b")
_UNTRUSTED_LIMIT = 2000


def redact_untrusted(text: str) -> str:
    """Redact stderr / harness errors / MCP errors / environment fixtures."""
    if not text:
        return text
    return sanitize_external_text(text, limit=_UNTRUSTED_LIMIT, include_environment=True)


def redact_text(text: str) -> str:
    return redact_untrusted(text)


def redact_evidence_text(text: str) -> str:
    if not text:
        return text
    for secret in environment_secrets():
        text = text.replace(secret, REDACTED)
    text = _JWT_RE.sub(REDACTED, text)
    text = _PREFIXED_SECRET_RE.sub(REDACTED, text)
    text = _EMAIL.sub(REDACTED, text)
    text = _MASTERMIND_ENV.sub(REDACTED, text)
    return text


def _walk(value: Any, text_fn) -> Any:
    if isinstance(value, str):
        if any(marker in value.upper() for marker in _SECRET_MARKERS) and (
            "=" in value or value.startswith("sk-") or "TOKEN" in value.upper()
        ):
            return REDACTED
        return text_fn(value)
    if isinstance(value, dict):
        out: dict[Any, Any] = {}
        for key, item in value.items():
            safe_key = text_fn(str(key)) if isinstance(key, str) else key
            if isinstance(key, str) and any(marker in key.upper() for marker in _SECRET_MARKERS):
                out[safe_key] = REDACTED
            else:
                out[safe_key] = _walk(item, text_fn)
        return out
    if isinstance(value, list):
        return [_walk(item, text_fn) for item in value]
    if isinstance(value, tuple):
        return tuple(_walk(item, text_fn) for item in value)
    return value


def redact_value(value: Any) -> Any:
    """Deep-redact an untrusted payload (errors, env, stderr)."""
    return _walk(value, redact_untrusted)


def redact_evidence(value: Any) -> Any:
    """Deep-redact a finished probe without eating SHA-256 digests."""
    return _walk(value, redact_evidence_text)


def evidence_contains_secret(value: Any) -> bool:
    """True when finished evidence still contains credential-shaped material."""
    if isinstance(value, str):
        return value != redact_evidence_text(value)
    if isinstance(value, dict):
        return any(
            evidence_contains_secret(key) or evidence_contains_secret(item)
            for key, item in value.items()
        )
    if isinstance(value, (list, tuple)):
        return any(evidence_contains_secret(item) for item in value)
    return False
