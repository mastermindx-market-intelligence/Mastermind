"""Bounded JSON consumption shared by the existing review HTTP adapters.

This helper has no credentials, destinations, retry policy or effect authority.
The caller owns the response context and closes it on every exit.
"""
from __future__ import annotations

import json
from collections.abc import Callable

import httpx


class BoundedResponseError(RuntimeError):
    """A fixed, opaque response failure code."""


def bounded_json(
    response: httpx.Response, *, max_bytes: int,
    deadline: float, clock: Callable[[], float],
) -> object:
    """Retain at most max_bytes, without decoding gzip or buffering error bodies.

HTTPX timeouts bound an individual I/O wait. The monotonic deadline additionally
stops consumption between chunks; it cannot interrupt a running synchronous I/O.
"""
    encoding = response.headers.get("content-encoding", "identity").strip().lower()
    if encoding not in {"", "identity"}:
        raise BoundedResponseError("GITHUB_RESPONSE_ENCODING_REFUSED")
    length = response.headers.get("content-length")
    if length is not None:
        if not length.isascii() or not length.isdigit() or len(length) > 10:
            raise BoundedResponseError("GITHUB_RESPONSE_INVALID")
        if int(length) > max_bytes:
            raise BoundedResponseError("GITHUB_RESPONSE_OVER_BOUND")
    if clock() >= deadline:
        raise BoundedResponseError("GITHUB_READ_BUDGET_EXHAUSTED")
    if response.is_stream_consumed:
        # Injected/mock responses may already be buffered. Production uses stream().
        raw = response.content
        if len(raw) > max_bytes:
            raise BoundedResponseError("GITHUB_RESPONSE_OVER_BOUND")
    else:
        raw = bytearray()
        # Do not ask HTTPX to aggregate a fixed-size chunk: a slow stream could
        # otherwise drip bytes for many I/O timeouts before we see the clock.
        for chunk in response.iter_raw():
            if clock() >= deadline:
                raise BoundedResponseError("GITHUB_READ_BUDGET_EXHAUSTED")
            if len(raw) + len(chunk) > max_bytes:
                raise BoundedResponseError("GITHUB_RESPONSE_OVER_BOUND")
            raw.extend(chunk)
    try:
        result = json.loads(raw)
    except (ValueError, UnicodeError, RecursionError):
        raise BoundedResponseError("GITHUB_RESPONSE_INVALID") from None
    if clock() >= deadline:
        raise BoundedResponseError("GITHUB_READ_BUDGET_EXHAUSTED")
    return result
