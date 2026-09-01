"""Canonical bytes, digests, and primitive grammar for EVAL-R0.

Implements design §6.1/§6.2 and plan §5.4: strict canonical JSON (no float,
no tuple, no non-string key, no NaN/infinity, no silent coercion), whole
second UTC timestamps, prefixed UUID4 IDs, source-qualified refs, and
sha256 digesting of a document with its own digest field excluded.

Standard library only. No import of any other ``scripts.agent_eval``
submodule other than :mod:`scripts.agent_eval.errors`.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from scripts.agent_eval.errors import ContractDefect, ContractError

_INT_MIN = -(2**63)
_INT_MAX = 2**63 - 1

_UTC_Z_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})Z$")
_SOURCE_REF_RE = re.compile(r"^git:[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+@[0-9a-f]{40}$")
_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_DECIMAL_RE = re.compile(r"^-?(0|[1-9][0-9]*)(\.[0-9]+)?$")


def _walk_canonical(value: Any, path: str):
    if value is None:
        return
    if isinstance(value, bool):
        return
    if isinstance(value, int):
        if not (_INT_MIN <= value <= _INT_MAX):
            yield ContractDefect(path, "INT_OUT_OF_RANGE", "integer is out of signed 64-bit range")
        return
    if isinstance(value, float):
        yield ContractDefect(path, "FLOAT_NOT_ALLOWED", "float values are not canonical; use a decimal string")
        return
    if isinstance(value, str):
        if unicodedata.normalize("NFC", value) != value:
            yield ContractDefect(path, "STRING_NOT_NFC", "string is not NFC-normalized")
        return
    if isinstance(value, tuple):
        yield ContractDefect(path, "TUPLE_NOT_ALLOWED", "tuples are not canonical; use a list")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            yield from _walk_canonical(item, f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                yield ContractDefect(path, "NON_STRING_KEY", f"dict key {key!r} is not a string")
                continue
            if unicodedata.normalize("NFC", key) != key:
                yield ContractDefect(path, "KEY_NOT_NFC", f"dict key {key!r} is not NFC-normalized")
            yield from _walk_canonical(item, f"{path}.{key}")
        return
    yield ContractDefect(path, "UNSUPPORTED_TYPE", f"unsupported type {type(value).__name__}")


def require_canonical_json_tree(value: Any, path: str = "$") -> None:
    """Raise :class:`ContractError` if ``value`` is not canonical-JSON-safe.

    Accepted: JSON null, exact bool, signed 64-bit int, NFC string, list,
    dict with string keys. Rejected: float, tuple, non-string key,
    out-of-range int, NaN/infinity (caught as float), silent coercion.
    """
    defects = list(_walk_canonical(value, path))
    if defects:
        raise ContractError(defects)


def canonical_json_bytes(value: Any) -> bytes:
    """Sorted, compact UTF-8 canonical JSON bytes for ``value``."""
    require_canonical_json_tree(value)
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")


def digest_value(value: Any) -> str:
    """``sha256:<64 lower-case hex>`` over the canonical bytes of ``value``."""
    return "sha256:" + hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def digest_document(document: dict, digest_field: str) -> str:
    """Digest ``document`` with its own ``digest_field`` excluded."""
    if not isinstance(document, dict):
        raise ContractError([ContractDefect("$", "NOT_A_DOCUMENT", "document must be a JSON object")])
    stripped = {key: val for key, val in document.items() if key != digest_field}
    return digest_value(stripped)


def add_document_digest(document: dict, digest_field: str) -> dict:
    """Return a new dict equal to ``document`` with ``digest_field`` set."""
    digest = digest_document(document, digest_field)
    result = dict(document)
    result[digest_field] = digest
    return result


def verify_document_digest(document: dict, digest_field: str) -> None:
    """Raise :class:`ContractError` unless ``document[digest_field]`` matches."""
    if not isinstance(document, dict) or digest_field not in document:
        raise ContractError(
            [ContractDefect(f"$.{digest_field}", "DIGEST_MISSING", "document is missing its own digest field")]
        )
    expected = digest_document(document, digest_field)
    actual = document[digest_field]
    if actual != expected:
        raise ContractError(
            [ContractDefect(f"$.{digest_field}", "DIGEST_MISMATCH", "stored digest does not match recomputed digest")]
        )


def parse_utc_z(value: Any, path: str = "$") -> datetime:
    """Parse a strict whole-second ``YYYY-MM-DDTHH:MM:SSZ`` UTC timestamp."""
    if not isinstance(value, str):
        raise ContractError([ContractDefect(path, "TIMESTAMP_NOT_STRING", "timestamp must be a string")])
    match = _UTC_Z_RE.match(value)
    if not match:
        raise ContractError(
            [ContractDefect(path, "TIMESTAMP_SHAPE", "timestamp must match YYYY-MM-DDTHH:MM:SSZ")]
        )
    year, month, day, hour, minute, second = (int(part) for part in match.groups())
    try:
        return datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)
    except ValueError as exc:
        raise ContractError([ContractDefect(path, "TIMESTAMP_INVALID", str(exc))]) from exc


def parse_prefixed_uuid4(value: Any, prefix: str, path: str = "$") -> UUID:
    """Parse ``"<prefix>:<uuid4>"`` with a lower-case canonical uuid4 body."""
    if not isinstance(value, str):
        raise ContractError([ContractDefect(path, "ID_NOT_STRING", "id must be a string")])
    want_prefix = f"{prefix}:"
    if not value.startswith(want_prefix):
        raise ContractError([ContractDefect(path, "ID_PREFIX_MISMATCH", f"id must start with {want_prefix!r}")])
    raw = value[len(want_prefix):]
    if raw != raw.lower():
        raise ContractError([ContractDefect(path, "ID_NOT_LOWERCASE", "uuid segment must be lower-case")])
    try:
        parsed = UUID(raw)
    except ValueError as exc:
        raise ContractError([ContractDefect(path, "ID_NOT_UUID", "id segment is not a valid uuid")]) from exc
    if str(parsed) != raw or parsed.version != 4:
        raise ContractError([ContractDefect(path, "ID_NOT_UUID4", "id segment is not a canonical uuid4")])
    return parsed


def parse_source_qualified_ref(value: Any, path: str = "$") -> str:
    """Parse ``git:<owner>/<repo>@<40-hex-sha>``."""
    if not isinstance(value, str):
        raise ContractError(
            [ContractDefect(path, "SOURCE_REF_NOT_STRING", "source-qualified ref must be a string")]
        )
    if not _SOURCE_REF_RE.match(value):
        raise ContractError(
            [
                ContractDefect(
                    path,
                    "SOURCE_REF_SHAPE",
                    "source-qualified ref must match git:<owner>/<repo>@<40-hex-sha>",
                )
            ]
        )
    return value


def parse_digest_string(value: Any, path: str = "$") -> str:
    """Parse ``sha256:<64 lower-case hex>``."""
    if not isinstance(value, str) or not _DIGEST_RE.match(value):
        raise ContractError(
            [ContractDefect(path, "DIGEST_SHAPE", "digest must match sha256:<64 lower-case hex>")]
        )
    return value


def parse_decimal_string(value: Any, path: str = "$") -> str:
    """Parse a canonical decimal measurement string (no leading zero, no +)."""
    if not isinstance(value, str) or not _DECIMAL_RE.match(value):
        raise ContractError(
            [ContractDefect(path, "DECIMAL_SHAPE", "decimal measurement must be a canonical decimal string")]
        )
    return value
