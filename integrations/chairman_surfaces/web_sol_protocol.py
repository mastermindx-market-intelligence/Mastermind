"""Closed, production-inert protocol for the Web-Sol exact-surface adapter.

Pure validation owns no browser, transport, filesystem, lifecycle or retry
state. Structural validation is separate from action-time admission so clocks
are explicit and deterministic. An expiry field is not proof it was enforced.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any

PROBE_SCHEMA = "mastermind.web_sol_surface_probe.v1"
ACTION_SCHEMA = "mastermind.web_sol_surface_action.v1"
RECEIPT_SCHEMA = "mastermind.web_sol_surface_receipt.v1"
HELLO_SCHEMA = "mastermind.web_sol_transport_hello.v1"
HELLO_ACK_SCHEMA = "mastermind.web_sol_transport_hello_ack.v1"
INSTANCE_CONFIG_SCHEMA = "mastermind.web_sol_instance_config.v1"
TRANSPORT_CAPABILITY_SCHEMA = "mastermind.web_sol_transport_capabilities.v1"
TRANSPORT_PROTOCOL_MAJOR = 1
WEB_SOL_PACKAGE_VERSION = "0.1.0"
MAX_ACTION_TTL_SECONDS = 60
ALLOWED_FUTURE_SKEW_SECONDS = 5


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
    REQUEST_EXPIRED = "REQUEST_EXPIRED"
    REQUEST_NOT_YET_VALID = "REQUEST_NOT_YET_VALID"
    REQUEST_WINDOW_INVALID = "REQUEST_WINDOW_INVALID"
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
_TRANSPORT_KEYS = frozenset(
    {
        "schema",
        "protocol_major",
        "role",
        "adapter_instance_id",
        "client_package_version",
        "native_package_version",
        "extension_package_version",
        "capability_digest",
        "boot_nonce",
        "challenge_nonce",
    }
)
_TRANSPORT_ROLES = frozenset({"client", "extension"})
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
_SEMVER_RE = re.compile(
    r"^(?:0|[1-9][0-9]*)\."
    r"(?:0|[1-9][0-9]*)\."
    r"(?:0|[1-9][0-9]*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
_MAX_OPERATION_KEY = 256
_MIN_NONCE = 16
_MAX_NONCE = 128
_MAX_PACKAGE_VERSION = 64
_MAX_BINDING_REVISION = (1 << 63) - 1


def _error(path: str, message: str) -> WebSolProtocolError:
    return WebSolProtocolError(f"{path}: {message}")


def _walk_forbidden(value: Any, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            key_path = (
                f"{path}.{key}"
                if isinstance(key, str)
                else f"{path}.<non-string-key>"
            )
            if not isinstance(key, str):
                raise _error(key_path, "object keys must be strings")
            if key.lower() in _FORBIDDEN_KEYS:
                raise _error(key_path, f"forbidden field {key!r}")
            _walk_forbidden(child, key_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _walk_forbidden(child, f"{path}[{index}]")


def _require_exact_keys(
    value: Any,
    keys: frozenset[str],
    path: str,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise _error(path, "must be an object")
    actual = set(value)
    missing = keys - actual
    extra = actual - keys
    if missing:
        raise _error(path, f"missing keys: {', '.join(sorted(missing))}")
    if extra:
        raise _error(
            path,
            f"unknown keys: {', '.join(sorted(str(item) for item in extra))}",
        )
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
        raise _error(
            path,
            f"must be a {_MIN_NONCE}..{_MAX_NONCE} character whitespace-free string",
        )


def _require_nullable_nonce(value: Any, path: str) -> None:
    if value is not None:
        _require_nonce(value, path)


def _require_package_version(value: Any, path: str) -> None:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > _MAX_PACKAGE_VERSION
        or _SEMVER_RE.fullmatch(value) is None
    ):
        raise _error(path, "must be a bounded semantic version")


def transport_capability_digest() -> str:
    """Return the deterministic closed F2 transport capability digest."""

    document = {
        "schema": TRANSPORT_CAPABILITY_SCHEMA,
        "protocol_major": TRANSPORT_PROTOCOL_MAJOR,
        "package_version": WEB_SOL_PACKAGE_VERSION,
        "roles": sorted(_TRANSPORT_ROLES),
        "actions": sorted(action.value for action in SurfaceAction),
        "schemas": [
            ACTION_SCHEMA,
            HELLO_ACK_SCHEMA,
            HELLO_SCHEMA,
            RECEIPT_SCHEMA,
        ],
    }
    payload = json.dumps(
        document,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _validate_transport_message(
    value: Any,
    *,
    expected_schema: str,
    require_boot_nonce: bool,
) -> dict[str, Any]:
    message = _require_exact_keys(value, _TRANSPORT_KEYS, "$")
    _require_schema(message["schema"], expected_schema, "$.schema")
    if message["protocol_major"] != TRANSPORT_PROTOCOL_MAJOR:
        raise _error(
            "$.protocol_major",
            f"must equal {TRANSPORT_PROTOCOL_MAJOR}",
        )
    if message["role"] not in _TRANSPORT_ROLES:
        raise _error("$.role", "must be client or extension")
    _require_hex64(message["adapter_instance_id"], "$.adapter_instance_id")
    for field in (
        "client_package_version",
        "native_package_version",
        "extension_package_version",
    ):
        _require_package_version(message[field], f"$.{field}")
    _require_hex64(message["capability_digest"], "$.capability_digest")
    if require_boot_nonce:
        _require_nonce(message["boot_nonce"], "$.boot_nonce")
    else:
        _require_nullable_nonce(message["boot_nonce"], "$.boot_nonce")
    _require_nonce(message["challenge_nonce"], "$.challenge_nonce")
    return copy.deepcopy(message)


def build_transport_hello(
    *,
    role: str,
    adapter_instance_id: str,
    client_package_version: str,
    native_package_version: str,
    extension_package_version: str,
    capability_digest: str,
    boot_nonce: str | None,
    challenge_nonce: str,
) -> dict[str, Any]:
    """Build one structurally valid detached peer HELLO document."""

    return validate_transport_hello(
        {
            "schema": HELLO_SCHEMA,
            "protocol_major": TRANSPORT_PROTOCOL_MAJOR,
            "role": role,
            "adapter_instance_id": adapter_instance_id,
            "client_package_version": client_package_version,
            "native_package_version": native_package_version,
            "extension_package_version": extension_package_version,
            "capability_digest": capability_digest,
            "boot_nonce": boot_nonce,
            "challenge_nonce": challenge_nonce,
        }
    )


def validate_transport_hello(value: Any) -> dict[str, Any]:
    """Validate and detach one closed HELLO document."""

    return _validate_transport_message(
        value,
        expected_schema=HELLO_SCHEMA,
        require_boot_nonce=False,
    )


def build_transport_hello_ack(
    hello: dict[str, Any],
    *,
    boot_nonce: str,
) -> dict[str, Any]:
    """Build one ACK that preserves the peer identity and exact challenge."""

    accepted = validate_transport_hello(hello)
    _require_nonce(boot_nonce, "$.boot_nonce")
    accepted["schema"] = HELLO_ACK_SCHEMA
    accepted["boot_nonce"] = boot_nonce
    return validate_transport_hello_ack(accepted)


def validate_transport_hello_ack(value: Any) -> dict[str, Any]:
    """Validate and detach one closed ACK with a concrete host boot nonce."""

    return _validate_transport_message(
        value,
        expected_schema=HELLO_ACK_SCHEMA,
        require_boot_nonce=True,
    )


def _parse_zulu(value: Any, path: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise _error(path, "must be an ISO-8601 UTC timestamp ending in Z")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise _error(
            path,
            "must be an ISO-8601 UTC timestamp ending in Z",
        ) from exc
    if parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0:
        raise _error(path, "must be UTC")
    return parsed


def _require_action(value: Any, path: str) -> SurfaceAction:
    try:
        return SurfaceAction(value)
    except (ValueError, TypeError) as exc:
        raise _error(path, "must be INSPECT or FOREGROUND") from exc


def _validate_identity_fields(
    value: dict[str, Any],
    *,
    include_time: bool,
) -> SurfaceAction:
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


def _require_member(
    value: Any,
    allowed: frozenset[str],
    path: str,
    description: str,
) -> None:
    if not isinstance(value, str) or value not in allowed:
        raise _error(path, description)


def _validate_probe(value: Any) -> dict[str, Any]:
    _walk_forbidden(value, "$.observation")
    probe = _require_exact_keys(value, _PROBE_KEYS, "$.observation")
    _require_schema(probe["schema"], PROBE_SCHEMA, "$.observation.schema")
    for field in (
        "target_present",
        "exact_conversation_loaded",
        "page_responsive",
    ):
        _require_strict_bool(probe[field], f"$.observation.{field}")
    _require_member(
        probe["document_ready_state"],
        frozenset({"loading", "interactive", "complete"}),
        "$.observation.document_ready_state",
        "must be loading, interactive, or complete",
    )
    _require_member(
        probe["visibility"],
        frozenset({"visible", "hidden"}),
        "$.observation.visibility",
        "must be visible or hidden",
    )
    _require_member(
        probe["generation_state"],
        frozenset({"active", "idle", "unknown"}),
        "$.observation.generation_state",
        "must be active, idle, or unknown",
    )
    for field in (
        "composer_available",
        "auth_required",
        "provider_error_present",
    ):
        _require_nullable_bool(probe[field], f"$.observation.{field}")
    return probe


def validate_request(value: dict[str, Any]) -> dict[str, Any]:
    """Validate structure only and return a detached normalized copy."""

    _walk_forbidden(value)
    request = _require_exact_keys(value, _REQUEST_KEYS, "$")
    _require_schema(request["schema"], ACTION_SCHEMA, "$.schema")
    _validate_identity_fields(request, include_time=True)
    return copy.deepcopy(request)


def validate_action_window(
    value: dict[str, Any],
    *,
    now: datetime,
) -> dict[str, Any]:
    """Admit a fresh request against an explicit aware clock, without I/O.

    Call at the action boundary, not just when a request is constructed. A
    separate monotonic deadline must bound the subsequent transport exchange.
    Limits are protocol constants, never caller-selected authority fields.
    """

    request = validate_request(value)
    if (
        not isinstance(now, datetime)
        or now.tzinfo is None
        or now.utcoffset() is None
    ):
        raise _error("$.clock", "clock must be a timezone-aware datetime")
    current = now.astimezone(timezone.utc)
    issued = _parse_zulu(request["issued_at"], "$.issued_at")
    expires = _parse_zulu(request["expires_at"], "$.expires_at")
    if expires <= current:
        raise _error("$.expires_at", "request expired")
    if issued > current + timedelta(seconds=ALLOWED_FUTURE_SKEW_SECONDS):
        raise _error("$.issued_at", "request is in the future")
    if (expires - issued).total_seconds() > MAX_ACTION_TTL_SECONDS:
        raise _error("$.expires_at", "request ttl exceeds the protocol ceiling")
    return request


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
            raise _error(
                "$.status",
                "FOREGROUNDED_VERIFIED requires FOREGROUND action",
            )
        if not probe["exact_conversation_loaded"]:
            raise _error(
                "$.observation.exact_conversation_loaded",
                "must be true for FOREGROUNDED_VERIFIED",
            )
    return copy.deepcopy(receipt)
