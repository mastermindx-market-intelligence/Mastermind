"""Bounded exact-URL JWKS retrieval for Business MCP authentication.

The cache is process-memory only. It owns no discovery, durable cache, token
state, retry ledger, scheduler, credential, OAuth session, or authorization
policy. Every network read targets the one immutable ``ResourcePolicy.jwks_uri``.
"""
from __future__ import annotations

import asyncio
import json
import math
import re
from collections.abc import Callable, Mapping
from typing import Any, Protocol

import httpx

from integrations.business_mcp_auth.contracts import (
    AuthError,
    AuthErrorCode,
    ResourcePolicy,
)


JWKS_TIMEOUT_SECONDS = 5.0
MAX_JWKS_BYTES = 256 * 1024
MAX_JWKS_KEYS = 16

_KID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_BASE64URL_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
_ALLOWED_JWK_KEYS = frozenset(
    {"kid", "kty", "use", "alg", "n", "e", "x5c", "x5t", "x5t#S256"}
)
_ALLOWED_MEDIA_TYPES = frozenset(
    {"application/json", "application/jwk-set+json"}
)


class JwksFetcher(Protocol):
    async def fetch(
        self,
        *,
        url: str,
        timeout_seconds: float,
        max_bytes: int,
    ) -> bytes: ...


def _error(code: AuthErrorCode) -> AuthError:
    return AuthError(code)


def _valid_kid(value: object) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 128
        or value != value.strip()
        or _CONTROL_RE.search(value)
        or _KID_RE.fullmatch(value) is None
    ):
        raise _error(AuthErrorCode.KEY_NOT_FOUND)
    return value


def _exact_ascii_text(value: object, *, maximum: int) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > maximum
        or value != value.strip()
        or _CONTROL_RE.search(value)
    ):
        raise _error(AuthErrorCode.JWKS_REFUSED)
    try:
        value.encode("ascii")
    except UnicodeEncodeError:
        raise _error(AuthErrorCode.JWKS_REFUSED) from None
    return value


def _base64url_uint(value: object) -> str:
    token = _exact_ascii_text(value, maximum=8192)
    if _BASE64URL_RE.fullmatch(token) is None:
        raise _error(AuthErrorCode.JWKS_REFUSED)
    return token


def _certificate_chain(value: object) -> list[str]:
    if not isinstance(value, list) or not value or len(value) > 8:
        raise _error(AuthErrorCode.JWKS_REFUSED)
    return [_exact_ascii_text(item, maximum=16384) for item in value]


def _optional_thumbprint(value: object) -> str:
    return _exact_ascii_text(value, maximum=512)


def _normalize_jwk(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise _error(AuthErrorCode.JWKS_REFUSED)
    raw = dict(value)
    if not set(raw).issubset(_ALLOWED_JWK_KEYS):
        raise _error(AuthErrorCode.JWKS_REFUSED)
    if not {"kid", "kty", "n", "e"}.issubset(raw):
        raise _error(AuthErrorCode.JWKS_REFUSED)

    try:
        kid = _valid_kid(raw.get("kid"))
    except AuthError:
        raise _error(AuthErrorCode.JWKS_REFUSED) from None
    if raw.get("kty") != "RSA":
        raise _error(AuthErrorCode.JWKS_REFUSED)
    if "use" in raw and raw.get("use") != "sig":
        raise _error(AuthErrorCode.JWKS_REFUSED)
    if "alg" in raw and raw.get("alg") != "RS256":
        raise _error(AuthErrorCode.JWKS_REFUSED)

    normalized: dict[str, object] = {
        "kid": kid,
        "kty": "RSA",
        "n": _base64url_uint(raw.get("n")),
        "e": _base64url_uint(raw.get("e")),
    }
    if "use" in raw:
        normalized["use"] = "sig"
    if "alg" in raw:
        normalized["alg"] = "RS256"
    if "x5c" in raw:
        normalized["x5c"] = _certificate_chain(raw.get("x5c"))
    if "x5t" in raw:
        normalized["x5t"] = _optional_thumbprint(raw.get("x5t"))
    if "x5t#S256" in raw:
        normalized["x5t#S256"] = _optional_thumbprint(raw.get("x5t#S256"))
    return normalized


def _copy_jwk(value: Mapping[str, object]) -> dict[str, object]:
    """Return a caller-owned copy of the closed JWK shape."""

    return {
        name: list(item) if isinstance(item, list) else item
        for name, item in value.items()
    }


def _parse_jwks(payload: bytes) -> dict[str, dict[str, object]]:
    if not isinstance(payload, bytes) or not payload or len(payload) > MAX_JWKS_BYTES:
        raise _error(AuthErrorCode.JWKS_REFUSED)
    try:
        value = json.loads(payload.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError):
        raise _error(AuthErrorCode.JWKS_REFUSED) from None
    if not isinstance(value, Mapping) or set(value) != {"keys"}:
        raise _error(AuthErrorCode.JWKS_REFUSED)
    raw_keys = value.get("keys")
    if (
        not isinstance(raw_keys, list)
        or not raw_keys
        or len(raw_keys) > MAX_JWKS_KEYS
    ):
        raise _error(AuthErrorCode.JWKS_REFUSED)

    result: dict[str, dict[str, object]] = {}
    for raw_key in raw_keys:
        key = _normalize_jwk(raw_key)
        kid = str(key["kid"])
        if kid in result:
            raise _error(AuthErrorCode.JWKS_REFUSED)
        result[kid] = key
    return result


def _monotonic_value(monotonic: Callable[[], float]) -> float:
    try:
        value = monotonic()
    except Exception:
        raise _error(AuthErrorCode.INTERNAL_ERROR) from None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _error(AuthErrorCode.INTERNAL_ERROR)
    number = float(value)
    if not math.isfinite(number):
        raise _error(AuthErrorCode.INTERNAL_ERROR)
    return number


class HttpxJwksFetcher:
    """One strict HTTPS GET against the policy-owned JWKS URL."""

    def __init__(self, policy: ResourcePolicy) -> None:
        if not isinstance(policy, ResourcePolicy):
            raise TypeError("policy must be ResourcePolicy")
        self._policy = policy

    async def fetch(
        self,
        *,
        url: str,
        timeout_seconds: float,
        max_bytes: int,
    ) -> bytes:
        if (
            url != self._policy.jwks_uri
            or timeout_seconds != JWKS_TIMEOUT_SECONDS
            or max_bytes != MAX_JWKS_BYTES
        ):
            raise _error(AuthErrorCode.JWKS_UNAVAILABLE)
        try:
            async with httpx.AsyncClient(
                follow_redirects=False,
                trust_env=False,
                timeout=timeout_seconds,
            ) as client:
                async with client.stream(
                    "GET",
                    url,
                    headers={"Accept": "application/json"},
                ) as response:
                    if response.status_code != 200:
                        raise _error(AuthErrorCode.JWKS_UNAVAILABLE)
                    content_type = response.headers.get("content-type")
                    if not isinstance(content_type, str):
                        raise _error(AuthErrorCode.JWKS_UNAVAILABLE)
                    media_type = content_type.split(";", 1)[0].strip().lower()
                    if media_type not in _ALLOWED_MEDIA_TYPES:
                        raise _error(AuthErrorCode.JWKS_UNAVAILABLE)
                    chunks: list[bytes] = []
                    total = 0
                    async for chunk in response.aiter_bytes():
                        if not isinstance(chunk, bytes):
                            raise _error(AuthErrorCode.JWKS_UNAVAILABLE)
                        total += len(chunk)
                        if total > max_bytes:
                            raise _error(AuthErrorCode.JWKS_UNAVAILABLE)
                        chunks.append(chunk)
                    if total == 0:
                        raise _error(AuthErrorCode.JWKS_UNAVAILABLE)
                    return b"".join(chunks)
        except AuthError:
            raise
        except Exception:
            raise _error(AuthErrorCode.JWKS_UNAVAILABLE) from None


class BoundedJwksCache:
    """Single-flight, process-memory JWKS cache with bounded refresh pressure."""

    def __init__(
        self,
        *,
        policy: ResourcePolicy,
        fetcher: JwksFetcher,
        monotonic: Callable[[], float],
    ) -> None:
        if not isinstance(policy, ResourcePolicy):
            raise TypeError("policy must be ResourcePolicy")
        if not callable(getattr(fetcher, "fetch", None)) or not callable(monotonic):
            raise TypeError("fetcher and monotonic are required")
        self._policy = policy
        self._fetcher = fetcher
        self._monotonic = monotonic
        self._lock = asyncio.Lock()
        self._keys: dict[str, dict[str, object]] = {}
        self._fetched_at: float | None = None
        self._last_unknown_kid_refresh_at: float | None = None
        self._fetch_retry_not_before: float | None = None

    def _is_fresh(self, now: float) -> bool:
        if self._fetched_at is None:
            return False
        age = now - self._fetched_at
        return 0 <= age <= self._policy.jwks_cache_ttl_seconds

    async def _fetch_replacement(self, now: float) -> None:
        if (
            self._fetch_retry_not_before is not None
            and now < self._fetch_retry_not_before
        ):
            raise _error(AuthErrorCode.JWKS_UNAVAILABLE)
        try:
            payload = await self._fetcher.fetch(
                url=self._policy.jwks_uri,
                timeout_seconds=JWKS_TIMEOUT_SECONDS,
                max_bytes=MAX_JWKS_BYTES,
            )
        except AuthError as exc:
            if exc.code is AuthErrorCode.JWKS_REFUSED:
                raise
            self._fetch_retry_not_before = (
                now + self._policy.fetch_failure_backoff_seconds
            )
            raise _error(AuthErrorCode.JWKS_UNAVAILABLE) from None
        except Exception:
            self._fetch_retry_not_before = (
                now + self._policy.fetch_failure_backoff_seconds
            )
            raise _error(AuthErrorCode.JWKS_UNAVAILABLE) from None

        try:
            replacement = _parse_jwks(payload)
        except AuthError:
            self._fetch_retry_not_before = (
                now + self._policy.fetch_failure_backoff_seconds
            )
            raise
        except Exception:
            self._fetch_retry_not_before = (
                now + self._policy.fetch_failure_backoff_seconds
            )
            raise _error(AuthErrorCode.JWKS_UNAVAILABLE) from None

        self._keys = replacement
        self._fetched_at = now
        self._fetch_retry_not_before = None

    async def key_for(self, kid: str) -> dict[str, object]:
        """Return a copy of one exact RSA public JWK or a typed refusal."""

        key_id = _valid_kid(kid)
        async with self._lock:
            now = _monotonic_value(self._monotonic)
            fresh = self._is_fresh(now)
            if fresh and key_id in self._keys:
                return _copy_jwk(self._keys[key_id])

            if fresh:
                last = self._last_unknown_kid_refresh_at
                if (
                    last is not None
                    and now - last
                    < self._policy.unknown_kid_refresh_cooldown_seconds
                ):
                    raise _error(AuthErrorCode.KEY_NOT_FOUND)
                self._last_unknown_kid_refresh_at = now
                await self._fetch_replacement(now)
                if key_id not in self._keys:
                    raise _error(AuthErrorCode.KEY_NOT_FOUND)
                return _copy_jwk(self._keys[key_id])

            had_stale_generation = self._fetched_at is not None
            await self._fetch_replacement(now)
            if had_stale_generation:
                # A full stale-generation refresh is also the one allowed
                # network read for immediately following unknown kids.
                self._last_unknown_kid_refresh_at = now
            if key_id not in self._keys:
                self._last_unknown_kid_refresh_at = now
                raise _error(AuthErrorCode.KEY_NOT_FOUND)
            return _copy_jwk(self._keys[key_id])


__all__ = [
    "JWKS_TIMEOUT_SECONDS",
    "MAX_JWKS_BYTES",
    "MAX_JWKS_KEYS",
    "BoundedJwksCache",
    "HttpxJwksFetcher",
    "JwksFetcher",
]
