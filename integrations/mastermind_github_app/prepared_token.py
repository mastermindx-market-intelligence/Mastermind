"""Storeless app-local authenticated prepared tokens for GitHub branch patches."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import zlib
from collections.abc import Mapping
from typing import Any


TOKEN_PREFIX = "mmx-ghp2-v1"
MAX_TOKEN_CHARS = 400_000
MAX_DECOMPRESSED_BYTES = 200_000


class PreparedTokenError(ValueError):
    """Payload-free token refusal."""

    def __init__(self) -> None:
        super().__init__("prepared_token_invalid")


def canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    if not value or any(ord(char) > 127 for char in value):
        raise PreparedTokenError()
    padding = "=" * ((4 - len(value) % 4) % 4)
    try:
        return base64.b64decode(
            (value + padding).encode("ascii"),
            altchars=b"-_",
            validate=True,
        )
    except (ValueError, UnicodeError) as exc:
        raise PreparedTokenError() from exc


class HmacPreparedTokenCodec:
    """Encode authenticated self-contained tokens without a prepared-action store."""

    def __init__(self, secret: bytes, *, context: str) -> None:
        if not isinstance(secret, bytes) or len(secret) < 32:
            raise ValueError("secret must contain at least 32 bytes")
        if not isinstance(context, str) or not context or len(context) > 200:
            raise ValueError("context must be a non-empty bounded string")
        self._secret = bytes(secret)
        self._context = context.encode("utf-8")

    def encode(self, payload: Mapping[str, Any]) -> str:
        if not isinstance(payload, Mapping):
            raise PreparedTokenError()
        raw = canonical_json(dict(payload))
        if len(raw) > MAX_DECOMPRESSED_BYTES:
            raise PreparedTokenError()
        compressed = zlib.compress(raw, level=9)
        signed = self._signed_bytes(compressed)
        signature = hmac.new(self._secret, signed, hashlib.sha256).digest()
        token = f"{TOKEN_PREFIX}.{_b64encode(compressed)}.{_b64encode(signature)}"
        if len(token) > MAX_TOKEN_CHARS:
            raise PreparedTokenError()
        return token

    def decode(self, token: object) -> dict[str, Any]:
        if not isinstance(token, str) or not token or len(token) > MAX_TOKEN_CHARS:
            raise PreparedTokenError()
        parts = token.split(".")
        if len(parts) != 3 or parts[0] != TOKEN_PREFIX:
            raise PreparedTokenError()
        compressed = _b64decode(parts[1])
        supplied_signature = _b64decode(parts[2])
        if len(supplied_signature) != hashlib.sha256().digest_size:
            raise PreparedTokenError()
        expected_signature = hmac.new(
            self._secret,
            self._signed_bytes(compressed),
            hashlib.sha256,
        ).digest()
        if not hmac.compare_digest(supplied_signature, expected_signature):
            raise PreparedTokenError()

        decompressor = zlib.decompressobj()
        try:
            raw = decompressor.decompress(compressed, MAX_DECOMPRESSED_BYTES + 1)
            if len(raw) > MAX_DECOMPRESSED_BYTES or decompressor.unconsumed_tail:
                raise PreparedTokenError()
            remaining = MAX_DECOMPRESSED_BYTES + 1 - len(raw)
            flushed = decompressor.flush(remaining)
            raw += flushed
        except (ValueError, zlib.error) as exc:
            raise PreparedTokenError() from exc
        if (
            len(raw) > MAX_DECOMPRESSED_BYTES
            or not decompressor.eof
            or decompressor.unused_data
            or decompressor.unconsumed_tail
        ):
            raise PreparedTokenError()
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise PreparedTokenError() from exc
        if not isinstance(value, dict):
            raise PreparedTokenError()
        return value

    def _signed_bytes(self, compressed: bytes) -> bytes:
        return TOKEN_PREFIX.encode("ascii") + b"\0" + self._context + b"\0" + compressed


__all__ = [
    "MAX_DECOMPRESSED_BYTES",
    "MAX_TOKEN_CHARS",
    "TOKEN_PREFIX",
    "HmacPreparedTokenCodec",
    "PreparedTokenError",
    "canonical_json",
]
