"""Closed, production-inert protocol for the Web-Sol exact-surface adapter.

This module is deliberately pure validation.  It owns no browser access,
transport, filesystem state, lifecycle state, Wake behavior, target selection,
or retry/failover.  Callers must resolve the exact surface before composing a
request.
"""
from __future__ import annotations

import copy
import re
import uuid
from datetime import datetime
from enum import Enum
from typing import Any

PROBE_SCHEMA = "mastermind.web_sol_surface_probe.v1"
ACTION_SCHEMA = "mastermind.web_sol_surface_action.v1"
RECEIPT_SCHEMA = "mastermind.web_sol_surface_receipt.v1"


class WebSolProtocolError(ValueError):
    """A Web-Sol protocol value failed the closed contract."""


class SurfaceAction(str, Enum):
    INSPECT = "INSPECT"
    FOREGROUND = "FOREGROUND"


class ReceiptStatus(str, Enum):
    INSPECTED = "INSPECTED"
    FOREGROUNDED_VERIFIED = "FOREGROUNDED_VERIFIED"
    TARGET_NOT_FOUND = "TARGET_NOT_FOUND"
    TARGET_CHANGED = "TARGET_CHANGED"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    PROVIDER_ERROR = "PROVIDER_ERROR"
    UNSUPPORTED = "UNSUPPORTED"
    AMBIGUOUS_TARGET = "AMBIGUOUS_TARGET"
    UNKNOWN = "UNKNOWN"


_REQUEST_KEYS = frozenset(
    {
        "schema",
        "binding_id",
        "conversation_fingerprint",
        "binding_fingerprint",
        "binding_revision",
        "action",
        "operation_key",
        "issued_at",
        "expires_at",
        "nonce",
    }
)

_RECEIPT_KEYS = frozenset(
    {
        "schema",
        "binding_id",
        "conversation_fingerprint",
        "binding_fingerprint",
        "binding_revision",
        "action",
        "operation_key",
        "nonce",
        "status",
        "observed_at",
        "observation",
    }
)

_PROBE_KEYS = frozenset(
    {
        "schema",
        "target_present",
        "exact_conversation_loaded",
        "page_responsive",
        "document_ready_state",
        "visibility",
        "composer_available",
        "generation_state",
        "auth_required",
        "provider_error_present",
    }
)

# Belt-and-suspenders guard.  Closed-key validation would reject these anyway,
# but naming forbidden semantic/content fields explicitly makes violations
# diagnosable and prevents a later schema widening from silently admitting them.
_FORBIDDEN_KEYS = frozenset(
    {
        "transcript",
        "output",
        "raw_dom",
        "cookie",
        "cookies",
        "storage",
        "clipboard",
        "prompt",
        "message",
        "text",
        "selector",
        "script",
        "coordinates",
        "shell",
        "argv",
        "host_ref",
        "provider",
        "account",
        "profile_id",
        "folder_id",
        "url",
        "retry",
        "failover",
        "proxy",
        "fingerprint",
    }
)

_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_OPERATION_KEY = 256
_MIN_NONCE = 16
_MAX_NONCE = 128
_MAX_BINDING_REVISION = (1 << 63) - 1


def _error(path: str, message: str) -> WebSolProtocolError:
    return WebSolProtocolError(f"{path}: {message}")


def _walk_forbidden(value: Any, path: str = "$" ) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            key_path = f"{path}.{key}" if isinstance(key, str) else f"{path}.<non-string-key>"
            if not isinstance(key, str):
                raise _error(key_path, "object keys must be strings")
            if key.lower() in _FORBIDDEN_KEYS:
                raise _error(key_path, f"forbidden field {key!r}")
            _walk_forbidden(child, key_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _walk_forbidden(child, f"{path}[{index}]")


def _require_exact_keys(value: Any, keys: frozenset[str], path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise _error(path, "must be an object")
    actual = set(value)
    missing = keys - actual
    extra = actual - keys
    if missing:
        raise _error(path, f"missing keys: {', '.join(sorted(missing))}")
    if extra:
        raise _error(path, f"unknown keys: {', '.join(sorted(str(item) for item in extra))}")
    return value


def _require_schema(value: Any, expected: str, path: str) -> None:
    if value != expected:
        raise _error(path, f"must equal {expected!r}")


def _require_uuid(value: Any, path: str) -> None:
    if not isinstance(value, str):
        raise _error(path, "must be a UUID string")
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError) as exc:
        raise _error(path, "must be a UUID string") from exc
    if str(parsed) != value.lower():
        raise _error(path, "must be a canonical UUID string")


def _require_hex64(value: Any, path: str) -> None:
    if not isinstance(value, str) or not _HEX64_RE.fullmatch(value):
        raise _error(path, "must be 64 lowercase hexadecimal characters")


def _require_revision(value: Any, path: str) -> None:
    if type(value) is not int or not 0 <= value <= _MAX_BINDING_REVISION:
        raise _error(path, "must be a non-negative integer")


def _require_operation_key(value: Any, path: str) -> None:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > _MAX_OPERATION_KEY
        or any(character.isspace() for character in value)
    ):
        raise _error(path, "must be a non-empty, whitespace-free bounded string")


def _require_nonce(value: Any, path: str) -> None:
    if (
        not isinstance(value, str)
        or not _MIN_NONCE <= len(value) <= _MAX_NONCE
        or any(character.isspace() for character in value)
    ):
        raise _error(path, f"must be a {_MIN_NONCE}..{_MAX_NONCE} character whitespace-free string")


def _parse_zulu(value: Any, path: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise _error(path, "must be an ISO-8601 UTC timestamp ending in Z")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise _error(path, "must be an ISO-8601 UTC timestamp ending in Z") from exc
    if parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0:
        raise _error(path, "must be UTC")
    return parsed


def _require_action(value: Any, path: str) -> SurfaceAction:
    try:
        return SurfaceAction(value)
    except (ValueError, TypeError) as exc:
        raise _error(path, "must be INSPECT or FOREGROUND") from exc


def _validate_identity_fields(value: dict[str, Any], *, include_time: bool) -> SurfaceAction:
    _require_uuid(value["binding_id"], "$.binding_id")
    _require_hex64(value["conversation_fingerprint"], "$.conversation_fingerprint")
    _require_hex64(value["binding_fingerprint"], "$.binding_fingerprint")
    _require_revision(value["binding_revision"], "$.binding_revision")
    action = _require_action(value["action"], "$.action")
    _require_operation_key(value["operation_key"], "$.operation_key")
    _require_nonce(value["nonce"], "$.nonce")
    if include_time:
        issued = _parse_zulu(value["issued_at"], "$.issued_at")
        expires = _parse_zulu(value["expires_at"], "$.expires_at")
        if expires <= issued:
            raise _error("$.expires_at", "must be later than issued_at")
    return action


def _require_strict_bool(value: Any, path: str) -> None:
    if type(value) is not bool:
        raise _error(path, "must be a boolean")


def _require_nullable_bool(value: Any, path: str) -> None:
    if value is not None and type(value) is not bool:
        raise _error(path, "must be a boolean or null")


def _validate_probe(value: Any) -> dict[str, Any]:
    _walk_forbidden(value, "$.observation")
    probe = _require_exact_keys(value, _PROBE_KEYS, "$.observation")
    _require_schema(probe["schema"], PROBE_SCHEMA, "$.observation.schema")

    for field in ("target_present", "exact_conversation_loaded", "page_responsive"):
        _require_strict_bool(probe[field], f"$.observation.{field}")

    if probe["document_ready_state"] not in {"loading", "interactive", "complete"}:
        raise _error(
            "$.observation.document_ready_state",
            "must be loading, interactive, or complete",
        )
    if probe["visibility"] not in {"visible", "hidden"}:
        raise _error("$.observation.visibility", "must be visible or hidden")
    if probe["generation_state"] not in {"active", "idle", "unknown"}:
        raise _error("$.observation.generation_state", "must be active, idle, or unknown")

    for field in ("composer_available", "auth_required", "provider_error_present"):
        _require_nullable_bool(probe[field], f"$.observation.{field}")
    return probe


def validate_request(value: dict[str, Any]) -> dict[str, Any]:
    """Validate one exact-surface request and return a detached normalized copy."""

    _walk_forbidden(value)
    request = _require_exact_keys(value, _REQUEST_KEYS, "$")
    _require_schema(request["schema"], ACTION_SCHEMA, "$.schema")
    _validate_identity_fields(request, include_time=True)
    return copy.deepcopy(request)


def validate_receipt(value: dict[str, Any]) -> dict[str, Any]:
    """Validate one bounded S0/S1 receipt and return a deep detached copy."""

    _walk_forbidden(value)
    receipt = _require_exact_keys(value, _RECEIPT_KEYS, "$")
    _require_schema(receipt["schema"], RECEIPT_SCHEMA, "$.schema")
    action = _validate_identity_fields(receipt, include_time=False)
    _parse_zulu(receipt["observed_at"], "$.observed_at")

    try:
        status = ReceiptStatus(receipt["status"])
    except (ValueError, TypeError) as exc:
        raise _error("$.status", "unknown receipt status") from exc

    probe = _validate_probe(receipt["observation"])
    if status is ReceiptStatus.FOREGROUNDED_VERIFIED:
        if action is not SurfaceAction.FOREGROUND:
            raise _error("$.status", "FOREGROUNDED_VERIFIED requires FOREGROUND action")
        if not probe["exact_conversation_loaded"]:
            raise _error(
                "$.observation.exact_conversation_loaded",
                "must be true for FOREGROUNDED_VERIFIED",
            )

    return copy.deepcopy(receipt)
