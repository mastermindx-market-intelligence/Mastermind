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

from control_plane.operator_harness_contract import ATTENTION_TURN_INSTRUCTION

PROBE_SCHEMA = "mastermind.web_sol_surface_probe.v1"
ACTION_SCHEMA = "mastermind.web_sol_surface_action.v1"
RECEIPT_SCHEMA = "mastermind.web_sol_surface_receipt.v1"
HELLO_SCHEMA = "mastermind.web_sol_transport_hello.v1"
HELLO_ACK_SCHEMA = "mastermind.web_sol_transport_hello_ack.v1"
INSTANCE_CONFIG_SCHEMA = "mastermind.web_sol_instance_config.v1"
TRANSPORT_CAPABILITY_SCHEMA = "mastermind.web_sol_transport_capabilities.v1"
TRANSPORT_PROTOCOL_MAJOR = 1
WEB_SOL_PACKAGE_VERSION = "0.5.0"
MAX_ACTION_TTL_SECONDS = 60
ALLOWED_FUTURE_SKEW_SECONDS = 5
CONTINUATION_DIRECTIVE_TEXT = (
    "SOL CONTINUE\n\n"
    "Continue the same logical responsibility.\n"
    "Recover current canonical state before acting; Project/chat history is advisory only.\n"
    "Do not restart completed work.\n"
    "Recover any open reciprocal worker dialogue before creating replacement work.\n"
    "Advance the highest-leverage unfinished critical-path capability within the existing authorized scope."
    "\n\n"
    + ATTENTION_TURN_INSTRUCTION
)
CONTINUATION_DIRECTIVE_DIGEST = hashlib.sha256(
    CONTINUATION_DIRECTIVE_TEXT.encode("utf-8")
).hexdigest()


class WebSolProtocolError(ValueError):
    """A Web-Sol protocol value failed the closed contract."""


class SurfaceAction(str, Enum):
    INSPECT = "INSPECT"
    FOREGROUND = "FOREGROUND"
    TYPED_REENTRY = "TYPED_REENTRY"
    SUBMIT_CONTINUATION = "SUBMIT_CONTINUATION"
    OBSERVE_CONTINUATION_ACK = "OBSERVE_CONTINUATION_ACK"


class ReceiptStatus(str, Enum):
    INSPECTED = "INSPECTED"
    FOREGROUNDED_VERIFIED = "FOREGROUNDED_VERIFIED"
    FOREGROUND_EFFECT_UNKNOWN = "FOREGROUND_EFFECT_UNKNOWN"
    CONSUMED = "CONSUMED"
    NOT_CONSUMED = "NOT_CONSUMED"
    CONVERSATION_CLOSED = "CONVERSATION_CLOSED"
    TYPED_REENTRY_BLOCKED = "TYPED_REENTRY_BLOCKED"
    CONTINUATION_NOT_SUBMITTED = "CONTINUATION_NOT_SUBMITTED"
    CONTINUATION_SUBMIT_EFFECT_UNKNOWN = "CONTINUATION_SUBMIT_EFFECT_UNKNOWN"
    CONTINUATION_STARTED = "CONTINUATION_STARTED"
    CONTINUATION_ACKNOWLEDGED = "CONTINUATION_ACKNOWLEDGED"
    CONTINUATION_ACK_PENDING = "CONTINUATION_ACK_PENDING"
    CONTINUATION_ACK_REFUSED = "CONTINUATION_ACK_REFUSED"
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
        "action",
        "operation_key",
        "issued_at",
        "expires_at",
        "nonce",
    }
)
_TYPED_REENTRY_PAYLOAD_KEYS = frozenset({
    "operation_id",
    "result_digest",
    "obligation_digest",
})
_TYPED_REENTRY_KEYS = _REQUEST_KEYS | _TYPED_REENTRY_PAYLOAD_KEYS
_CONTINUATION_IDENTITY_PAYLOAD_KEYS = frozenset({
    "turn_id",
    "directive_digest",
    "session_alias",
    "runtime_binding_id",
    "runtime_binding_generation",
    "runtime_binding_fingerprint",
    "wake_obligation_ids",
    "wake_obligation_digest",
})
_SUBMIT_CONTINUATION_PAYLOAD_KEYS = _CONTINUATION_IDENTITY_PAYLOAD_KEYS
_OBSERVE_CONTINUATION_ACK_PAYLOAD_KEYS = _CONTINUATION_IDENTITY_PAYLOAD_KEYS
_SUBMIT_CONTINUATION_KEYS = _REQUEST_KEYS | _SUBMIT_CONTINUATION_PAYLOAD_KEYS
_OBSERVE_CONTINUATION_ACK_KEYS = _REQUEST_KEYS | _OBSERVE_CONTINUATION_ACK_PAYLOAD_KEYS
_RECEIPT_KEYS = frozenset(
    {
        "schema",
        "binding_id",
        "conversation_fingerprint",
        "binding_fingerprint",
        "action",
        "operation_key",
        "nonce",
        "status",
        "observed_at",
        "observation",
    }
)
_TYPED_REENTRY_RECEIPT_KEYS = _RECEIPT_KEYS | _TYPED_REENTRY_PAYLOAD_KEYS
_SUBMIT_CONTINUATION_RECEIPT_KEYS = _RECEIPT_KEYS | _SUBMIT_CONTINUATION_PAYLOAD_KEYS
_SEMANTIC_ACK_RESULT_KEYS = frozenset({
    "provider_native_turn_id",
    "acknowledged_obligation_ids",
    "terminal_ack_trailer",
})
_OBSERVE_CONTINUATION_ACK_RECEIPT_KEYS = (
    _RECEIPT_KEYS | _OBSERVE_CONTINUATION_ACK_PAYLOAD_KEYS | _SEMANTIC_ACK_RESULT_KEYS
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
_WAKE_ID_RE = re.compile(r"^WAKE-[0-9a-f]{32}$")
_NUDGE_ID_RE = re.compile(r"^NUDGE-[0-9a-f]{32}$")
_TURN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{2,255}$")
_SESSION_ALIAS_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{2,255}$")
_RUNTIME_BINDING_ID_RE = re.compile(r"^bind-wsx-[0-9a-f]{48}$")
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
_MAX_WAKE_OBLIGATIONS = 32


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


def _require_turn_id(value: Any, path: str) -> None:
    if not isinstance(value, str) or _TURN_ID_RE.fullmatch(value) is None:
        raise _error(path, "must be a bounded opaque turn identity")


def _require_nudge_id(value: Any, path: str) -> None:
    if not isinstance(value, str) or _NUDGE_ID_RE.fullmatch(value) is None:
        raise _error(path, "must be a canonical Wake nudge identity")


def _canonical_wake_obligation_ids(value: Any, path: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)) or not value:
        raise _error(path, "must be a non-empty canonical Wake identity list")
    ids = tuple(value)
    if len(ids) > _MAX_WAKE_OBLIGATIONS:
        raise _error(path, "exceeds the Wake identity count ceiling")
    if any(not isinstance(item, str) or _WAKE_ID_RE.fullmatch(item) is None for item in ids):
        raise _error(path, "contains a malformed Wake identity")
    if ids != tuple(sorted(set(ids))):
        raise _error(path, "must be unique and canonical sorted order")
    return ids


def wake_obligation_digest(obligation_ids: Any) -> str:
    ids = _canonical_wake_obligation_ids(obligation_ids, "$.wake_obligation_ids")
    document = {
        "schema": "mastermind.web_sol_wake_obligation_set.v1",
        "obligation_ids": list(ids),
    }
    payload = json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _validate_wake_obligation_set(value: dict[str, Any]) -> tuple[str, ...]:
    ids = _canonical_wake_obligation_ids(value["wake_obligation_ids"], "$.wake_obligation_ids")
    _require_hex64(value["wake_obligation_digest"], "$.wake_obligation_digest")
    if value["wake_obligation_digest"] != wake_obligation_digest(ids):
        raise _error("$.wake_obligation_digest", "does not match the canonical Wake identity set")
    return ids


def _require_session_alias(value: Any, path: str) -> None:
    if not isinstance(value, str) or _SESSION_ALIAS_RE.fullmatch(value) is None:
        raise _error(path, "must be a bounded opaque session alias")


def _require_runtime_binding_id(value: Any, path: str) -> None:
    if not isinstance(value, str) or _RUNTIME_BINDING_ID_RE.fullmatch(value) is None:
        raise _error(path, "must be a canonical Web-Sol RuntimeBinding identity")


def _require_runtime_binding_generation(value: Any, path: str) -> None:
    if type(value) is not int or not 1 <= value <= 9007199254740991:
        raise _error(path, "must be a positive safe integer")


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
        "schemas": sorted(
            [
                "mastermind.web_sol_census_request.v1",
                "mastermind.web_sol_census_receipt.v1",
                "mastermind.web_sol_census_table.v1",
                ACTION_SCHEMA,
                HELLO_ACK_SCHEMA,
                HELLO_SCHEMA,
                INSTANCE_CONFIG_SCHEMA,
                PROBE_SCHEMA,
                RECEIPT_SCHEMA,
            ]
        ),
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
        raise _error(
            path,
            "must be INSPECT, FOREGROUND, TYPED_REENTRY, SUBMIT_CONTINUATION, "
            "or OBSERVE_CONTINUATION_ACK",
        ) from exc


def _validate_identity_fields(
    value: dict[str, Any],
    *,
    include_time: bool,
) -> SurfaceAction:
    _require_uuid(value["binding_id"], "$.binding_id")
    _require_hex64(value["conversation_fingerprint"], "$.conversation_fingerprint")
    _require_hex64(value["binding_fingerprint"], "$.binding_fingerprint")
    action = _require_action(value["action"], "$.action")
    _require_operation_key(value["operation_key"], "$.operation_key")
    _require_nonce(value["nonce"], "$.nonce")
    if include_time:
        issued = _parse_zulu(value["issued_at"], "$.issued_at")
        expires = _parse_zulu(value["expires_at"], "$.expires_at")
        if expires <= issued:
            raise _error("$.expires_at", "must be later than issued_at")
        if (expires - issued).total_seconds() > MAX_ACTION_TTL_SECONDS:
            raise _error("$.expires_at", "request ttl exceeds the protocol ceiling")
    if action is SurfaceAction.TYPED_REENTRY:
        for field in ("operation_id", "result_digest", "obligation_digest"):
            if field not in value:
                raise _error(f"$.{field}", "required for TYPED_REENTRY")
            _require_hex64(value[field], f"$.{field}")
    if action in {
        SurfaceAction.SUBMIT_CONTINUATION,
        SurfaceAction.OBSERVE_CONTINUATION_ACK,
    }:
        action_name = action.value
        for field in _CONTINUATION_IDENTITY_PAYLOAD_KEYS:
            if field not in value:
                raise _error(f"$.{field}", f"required for {action_name}")
        if action is SurfaceAction.OBSERVE_CONTINUATION_ACK:
            _require_nudge_id(value["turn_id"], "$.turn_id")
        else:
            _require_turn_id(value["turn_id"], "$.turn_id")
        _require_hex64(value["directive_digest"], "$.directive_digest")
        if value["directive_digest"] != CONTINUATION_DIRECTIVE_DIGEST:
            raise _error("$.directive_digest", "does not match the fixed continuation directive")
        _require_session_alias(value["session_alias"], "$.session_alias")
        _require_runtime_binding_id(value["runtime_binding_id"], "$.runtime_binding_id")
        _require_runtime_binding_generation(
            value["runtime_binding_generation"],
            "$.runtime_binding_generation",
        )
        _require_hex64(value["runtime_binding_fingerprint"], "$.runtime_binding_fingerprint")
        _validate_wake_obligation_set(value)
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


def validate_probe(value: dict[str, Any]) -> dict[str, Any]:
    """Validate one closed Web-Sol probe and return a detached copy."""

    return copy.deepcopy(_validate_probe(value))


def validate_request(value: dict[str, Any]) -> dict[str, Any]:
    """Validate structure only and return a detached normalized copy."""

    _walk_forbidden(value)
    action = value.get("action") if isinstance(value, dict) else None
    if action == SurfaceAction.TYPED_REENTRY.value:
        request_keys = _TYPED_REENTRY_KEYS
    elif action == SurfaceAction.SUBMIT_CONTINUATION.value:
        request_keys = _SUBMIT_CONTINUATION_KEYS
    elif action == SurfaceAction.OBSERVE_CONTINUATION_ACK.value:
        request_keys = _OBSERVE_CONTINUATION_ACK_KEYS
    else:
        request_keys = _REQUEST_KEYS
    request = _require_exact_keys(value, request_keys, "$")
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


def _require_probe_truth(condition: bool, path: str, message: str) -> None:
    if not condition:
        raise _error(path, message)


def _validate_semantic_ack_result(
    receipt: dict[str, Any],
    status: ReceiptStatus,
) -> None:
    provider_turn = receipt["provider_native_turn_id"]
    acknowledged = receipt["acknowledged_obligation_ids"]
    trailer = receipt["terminal_ack_trailer"]
    _require_strict_bool(trailer, "$.terminal_ack_trailer")
    if status is ReceiptStatus.CONTINUATION_ACKNOWLEDGED:
        _require_turn_id(provider_turn, "$.provider_native_turn_id")
        ids = _canonical_wake_obligation_ids(
            acknowledged,
            "$.acknowledged_obligation_ids",
        )
        if ids != tuple(receipt["wake_obligation_ids"]):
            raise _error(
                "$.acknowledged_obligation_ids",
                "must exactly match the requested Wake identity set",
            )
        if trailer is not True:
            raise _error("$.terminal_ack_trailer", "must be true for acknowledged ACK")
        return
    if provider_turn is not None:
        raise _error("$.provider_native_turn_id", "must be null without acknowledged ACK")
    if acknowledged != []:
        raise _error("$.acknowledged_obligation_ids", "must be empty without acknowledged ACK")
    if trailer is not False:
        raise _error("$.terminal_ack_trailer", "must be false without acknowledged ACK")


def _validate_receipt_semantics(
    *,
    action: SurfaceAction,
    status: ReceiptStatus,
    probe: dict[str, Any],
    receipt: dict[str, Any],
) -> None:
    if status is ReceiptStatus.INSPECTED:
        _require_probe_truth(
            action is SurfaceAction.INSPECT,
            "$.status",
            "INSPECTED requires INSPECT action",
        )
        _require_probe_truth(
            probe["target_present"] and probe["exact_conversation_loaded"],
            "$.observation.exact_conversation_loaded",
            "INSPECTED requires the exact target to be present and loaded",
        )
        _require_probe_truth(
            probe["auth_required"] is not True,
            "$.observation.auth_required",
            "must not be true for INSPECTED",
        )
        _require_probe_truth(
            probe["provider_error_present"] is not True,
            "$.observation.provider_error_present",
            "must not be true for INSPECTED",
        )
        return

    if status is ReceiptStatus.FOREGROUNDED_VERIFIED:
        _require_probe_truth(
            action is SurfaceAction.FOREGROUND,
            "$.status",
            "FOREGROUNDED_VERIFIED requires FOREGROUND action",
        )
        _require_probe_truth(
            probe["target_present"] and probe["exact_conversation_loaded"],
            "$.observation.exact_conversation_loaded",
            "FOREGROUNDED_VERIFIED requires the exact target to be present and loaded",
        )
        _require_probe_truth(
            probe["visibility"] == "visible",
            "$.observation.visibility",
            "must be visible for FOREGROUNDED_VERIFIED",
        )
        _require_probe_truth(
            probe["auth_required"] is not True,
            "$.observation.auth_required",
            "must not be true for FOREGROUNDED_VERIFIED",
        )
        _require_probe_truth(
            probe["provider_error_present"] is not True,
            "$.observation.provider_error_present",
            "must not be true for FOREGROUNDED_VERIFIED",
        )
        return

    if status is ReceiptStatus.FOREGROUND_EFFECT_UNKNOWN:
        _require_probe_truth(
            action is SurfaceAction.FOREGROUND,
            "$.status",
            "FOREGROUND_EFFECT_UNKNOWN requires FOREGROUND action",
        )
        return

    if status is ReceiptStatus.CONSUMED:
        _require_probe_truth(
            action is SurfaceAction.TYPED_REENTRY,
            "$.status",
            "CONSUMED requires TYPED_REENTRY action",
        )
        _require_probe_truth(
            probe["target_present"] and probe["exact_conversation_loaded"],
            "$.observation.exact_conversation_loaded",
            "CONSUMED requires the exact target to be present and loaded",
        )
        _require_probe_truth(
            probe["composer_available"] is True,
            "$.observation.composer_available",
            "must be true for CONSUMED",
        )
        _require_probe_truth(
            probe["generation_state"] == "idle",
            "$.observation.generation_state",
            "must be idle for CONSUMED",
        )
        _require_probe_truth(
            probe["auth_required"] is not True,
            "$.observation.auth_required",
            "must not be true for CONSUMED",
        )
        _require_probe_truth(
            probe["provider_error_present"] is not True,
            "$.observation.provider_error_present",
            "must not be true for CONSUMED",
        )
        return

    if status is ReceiptStatus.NOT_CONSUMED:
        _require_probe_truth(
            action is SurfaceAction.TYPED_REENTRY,
            "$.status",
            "NOT_CONSUMED requires TYPED_REENTRY action",
        )
        _require_probe_truth(
            probe["composer_available"] is not True
            or probe["generation_state"] != "idle",
            "$.observation",
            "requires composer or generation state to be unavailable",
        )
        return

    if status is ReceiptStatus.CONVERSATION_CLOSED:
        _require_probe_truth(
            action is SurfaceAction.TYPED_REENTRY,
            "$.status",
            "CONVERSATION_CLOSED requires TYPED_REENTRY action",
        )
        _require_probe_truth(
            not probe["exact_conversation_loaded"],
            "$.observation.exact_conversation_loaded",
            "must be false for CONVERSATION_CLOSED",
        )
        return

    if status is ReceiptStatus.TYPED_REENTRY_BLOCKED:
        _require_probe_truth(
            action is SurfaceAction.TYPED_REENTRY,
            "$.status",
            "TYPED_REENTRY_BLOCKED requires TYPED_REENTRY action",
        )
        return

    if status is ReceiptStatus.CONTINUATION_NOT_SUBMITTED:
        _require_probe_truth(
            action is SurfaceAction.SUBMIT_CONTINUATION,
            "$.status",
            "CONTINUATION_NOT_SUBMITTED requires SUBMIT_CONTINUATION action",
        )
        return

    if status is ReceiptStatus.CONTINUATION_SUBMIT_EFFECT_UNKNOWN:
        _require_probe_truth(
            action is SurfaceAction.SUBMIT_CONTINUATION,
            "$.status",
            "CONTINUATION_SUBMIT_EFFECT_UNKNOWN requires SUBMIT_CONTINUATION action",
        )
        return

    if status is ReceiptStatus.CONTINUATION_STARTED:
        _require_probe_truth(
            action is SurfaceAction.SUBMIT_CONTINUATION,
            "$.status",
            "CONTINUATION_STARTED requires SUBMIT_CONTINUATION action",
        )
        _require_probe_truth(
            probe["target_present"] and probe["exact_conversation_loaded"],
            "$.observation.exact_conversation_loaded",
            "CONTINUATION_STARTED requires the exact target to remain loaded",
        )
        _require_probe_truth(
            probe["generation_state"] == "active",
            "$.observation.generation_state",
            "must be active for CONTINUATION_STARTED",
        )
        _require_probe_truth(
            probe["auth_required"] is not True,
            "$.observation.auth_required",
            "must not be true for CONTINUATION_STARTED",
        )
        return

    if status in {
        ReceiptStatus.CONTINUATION_ACKNOWLEDGED,
        ReceiptStatus.CONTINUATION_ACK_PENDING,
        ReceiptStatus.CONTINUATION_ACK_REFUSED,
    }:
        _require_probe_truth(
            action is SurfaceAction.OBSERVE_CONTINUATION_ACK,
            "$.status",
            "semantic ACK status requires OBSERVE_CONTINUATION_ACK action",
        )
        _validate_semantic_ack_result(receipt, status)
        if status is ReceiptStatus.CONTINUATION_ACKNOWLEDGED:
            _require_probe_truth(
                probe["target_present"] and probe["exact_conversation_loaded"],
                "$.observation.exact_conversation_loaded",
                "acknowledged ACK requires the exact target to remain loaded",
            )
            _require_probe_truth(
                probe["auth_required"] is not True,
                "$.observation.auth_required",
                "must not require auth for acknowledged ACK",
            )
            _require_probe_truth(
                probe["provider_error_present"] is not True,
                "$.observation.provider_error_present",
                "must not report provider error for acknowledged ACK",
            )
        return

    if status is ReceiptStatus.TARGET_NOT_FOUND:
        _require_probe_truth(
            not probe["target_present"],
            "$.observation.target_present",
            "must be false for TARGET_NOT_FOUND",
        )
        return

    if status is ReceiptStatus.TARGET_CHANGED:
        _require_probe_truth(
            not probe["exact_conversation_loaded"],
            "$.observation.exact_conversation_loaded",
            "must be false for TARGET_CHANGED",
        )
        return

    if status is ReceiptStatus.AUTH_REQUIRED:
        _require_probe_truth(
            probe["auth_required"] is True,
            "$.observation.auth_required",
            "must be true for AUTH_REQUIRED",
        )
        return

    if status is ReceiptStatus.PROVIDER_ERROR:
        _require_probe_truth(
            probe["provider_error_present"] is True,
            "$.observation.provider_error_present",
            "must be true for PROVIDER_ERROR",
        )


def validate_receipt(value: dict[str, Any]) -> dict[str, Any]:
    """Validate one bounded S0/S1 receipt and return a deep detached copy."""

    _walk_forbidden(value)
    action = value.get("action") if isinstance(value, dict) else None
    if action == SurfaceAction.TYPED_REENTRY.value:
        receipt_keys = _TYPED_REENTRY_RECEIPT_KEYS
    elif action == SurfaceAction.SUBMIT_CONTINUATION.value:
        receipt_keys = _SUBMIT_CONTINUATION_RECEIPT_KEYS
    elif action == SurfaceAction.OBSERVE_CONTINUATION_ACK.value:
        receipt_keys = _OBSERVE_CONTINUATION_ACK_RECEIPT_KEYS
    else:
        receipt_keys = _RECEIPT_KEYS
    receipt = _require_exact_keys(value, receipt_keys, "$")
    _require_schema(receipt["schema"], RECEIPT_SCHEMA, "$.schema")
    action = _validate_identity_fields(receipt, include_time=False)
    _parse_zulu(receipt["observed_at"], "$.observed_at")
    try:
        status = ReceiptStatus(receipt["status"])
    except (ValueError, TypeError) as exc:
        raise _error("$.status", "unknown receipt status") from exc
    probe = _validate_probe(receipt["observation"])
    _validate_receipt_semantics(
        action=action, status=status, probe=probe, receipt=receipt
    )
    return copy.deepcopy(receipt)
