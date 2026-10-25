"""Closed request contract for one unarmed ACP currentness observation.

This module parses a bounded request. It does not read Runtime, retain a lease
token, authorize a tool, open a socket, or arm dispatch. The schema is
``mastermind.acp_control_currentness/v1``.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import math
import re
from typing import Any, Mapping, NoReturn

SCHEMA = "mastermind.acp_control_currentness/v1"
EVIDENCE_SCOPE = "controller_evidence_only"
MAX_REQUEST_BYTES = 4096
MAX_STRING_BYTES = 256
MAX_OBJECT_DEPTH = 1
MAX_OBSERVATION_BYTES = 8192
STATES = frozenset({"CURRENT", "NOT_CURRENT", "UNAVAILABLE"})
PHASES = frozenset({"startup", "discovery", "dispatch"})
DISPATCH_AUTHORIZED = False

REQUEST_KEYS = frozenset({
    "schema",
    "phase",
    "invocation_id",
    "raw_tool",
    "argument_digest",
    "request_digest",
    "original_identity",
    "child_correlation",
})
IDENTITY_KEYS = frozenset({
    "job_id",
    "attempt_id",
    "worker_id",
    "quota_class",
    "fence_generation",
})
CORRELATION_KEYS = frozenset({
    "connection_id",
    "catalog_digest",
    "definition_digest",
})
OBSERVATION_KEYS = frozenset({
    "schema",
    "disposition",
    "dispatch_authorized",
    "evidence_scope",
    "phase",
    "invocation_id",
    "observed_at_ms",
    "reason_code",
    "subject",
    "controller_observed",
    "expected_bindings",
    "child_correlation",
    "unverified_joins",
})
UNVERIFIED_JOINS = (
    "native_process_liveness",
    "artifact_ownership",
    "session_ownership",
    "child_connection",
    "launch_attestation_liveness",
)

ERROR_CODES = frozenset({
    "ATTACHMENT_INVALID",
    "ATTACHMENT_IDENTITY_MISMATCH",
    "COLLECTION_REFUSED",
    "CORRELATION_MISMATCH",
    "DIGEST_MISMATCH",
    "DUPLICATE_KEY",
    "FRAME_INVALID",
    "FRAME_TOO_LARGE",
    "LENGTH_EXCEEDED",
    "MISSING_FIELD",
    "NESTING_REFUSED",
    "NONFINITE",
    "RANGE_REFUSED",
    "TOKEN_REJECTED",
    "TYPE_INVALID",
    "UNKNOWN_FIELD",
})

_IDENTIFIER = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_DIGEST = re.compile(r"\A[0-9a-f]{64}\Z")
_MAX_FENCE = (1 << 63) - 1


class AcpContinuingAuthorityContractError(ValueError):
    """Closed contract refusal. The message is the code and nothing else."""

    def __init__(self, code: str) -> None:
        if code not in ERROR_CODES:
            raise ValueError("unknown ACP currentness contract code")
        super().__init__(code)
        self.code = code

    def __repr__(self) -> str:
        return f"AcpContinuingAuthorityContractError({self.code!r})"


def _closed(code: str) -> NoReturn:
    """Raise a contract refusal that retains no input, cause, or context."""

    error = AcpContinuingAuthorityContractError(code)
    try:
        raise error from None
    except AcpContinuingAuthorityContractError as raised:
        raised.__context__ = None
        raised.__cause__ = None
        raised.__suppress_context__ = True
        raise


def _reject_nonfinite(_value: str) -> Any:
    raise AcpContinuingAuthorityContractError("NONFINITE")


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if not isinstance(key, str):
            raise AcpContinuingAuthorityContractError("TYPE_INVALID")
        if key in result:
            raise AcpContinuingAuthorityContractError("DUPLICATE_KEY")
        result[key] = value
    return result


def _check_text(value: str, forbidden: str | None) -> None:
    if forbidden and forbidden in value:
        _closed("TOKEN_REJECTED")
    try:
        size = len(value.encode("utf-8"))
    except UnicodeError:
        _closed("FRAME_INVALID")
    if size > MAX_STRING_BYTES:
        _closed("LENGTH_EXCEEDED")


def _walk(value: Any, depth: int, forbidden: str | None) -> None:
    if isinstance(value, dict):
        if depth > MAX_OBJECT_DEPTH:
            _closed("NESTING_REFUSED")
        for key, item in value.items():
            if not isinstance(key, str):
                _closed("TYPE_INVALID")
            _check_text(key, forbidden)
            _walk(item, depth + 1, forbidden)
        return
    if isinstance(value, (list, tuple)):
        _closed("COLLECTION_REFUSED")
    if isinstance(value, bool) or value is None or isinstance(value, int):
        return
    if isinstance(value, str):
        _check_text(value, forbidden)
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            _closed("NONFINITE")
        _closed("TYPE_INVALID")
    _closed("TYPE_INVALID")


def _exact_keys(value: Mapping[str, Any], expected: frozenset[str]) -> None:
    present = set(value)
    if present - expected:
        raise AcpContinuingAuthorityContractError("UNKNOWN_FIELD")
    if expected - present:
        raise AcpContinuingAuthorityContractError("MISSING_FIELD")


def _identifier(value: Any) -> str:
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        raise AcpContinuingAuthorityContractError("TYPE_INVALID")
    return value


def _digest(value: Any) -> str:
    if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
        raise AcpContinuingAuthorityContractError("TYPE_INVALID")
    return value


def _fence(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise AcpContinuingAuthorityContractError("TYPE_INVALID")
    if value <= 0 or value > _MAX_FENCE:
        raise AcpContinuingAuthorityContractError("RANGE_REFUSED")
    return value


def request_correlation_material(parsed: Mapping[str, Any]) -> dict[str, Any]:
    """Closed digest material. ``request_digest`` is excluded."""

    identity = parsed["original_identity"]
    correlation = parsed["child_correlation"]
    return {
        "argument_digest": parsed["argument_digest"],
        "child_correlation": {
            "catalog_digest": correlation["catalog_digest"],
            "connection_id": correlation["connection_id"],
            "definition_digest": correlation["definition_digest"],
        },
        "invocation_id": parsed["invocation_id"],
        "original_identity": {
            "attempt_id": identity["attempt_id"],
            "fence_generation": identity["fence_generation"],
            "job_id": identity["job_id"],
            "quota_class": identity["quota_class"],
            "worker_id": identity["worker_id"],
        },
        "phase": parsed["phase"],
        "raw_tool": parsed["raw_tool"],
        "schema": parsed["schema"],
    }


def canonical_request_bytes(material: Mapping[str, Any]) -> bytes:
    """UTF-8 canonical JSON: sorted keys, compact, ensure_ascii false, no newline."""

    try:
        encoded = json.dumps(
            material,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError, UnicodeError):
        _closed("FRAME_INVALID")
    if encoded.endswith("\n"):
        _closed("FRAME_INVALID")
    try:
        return encoded.encode("utf-8")
    except UnicodeError:
        _closed("FRAME_INVALID")


def canonical_request_digest(material: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_request_bytes(material)).hexdigest()


def parse_observation_request(
    raw: bytes | bytearray,
    *,
    forbidden_exact: str | None = None,
) -> dict[str, Any]:
    """Parse one closed request. ``forbidden_exact`` is rejected, never echoed."""

    if type(raw) is bytearray:
        if len(raw) > MAX_REQUEST_BYTES:
            _closed("FRAME_TOO_LARGE")
        payload = bytes(raw)
    elif type(raw) is bytes:
        if len(raw) > MAX_REQUEST_BYTES:
            _closed("FRAME_TOO_LARGE")
        payload = raw
    else:
        _closed("TYPE_INVALID")
    forbidden = forbidden_exact if type(forbidden_exact) is str and forbidden_exact else None
    if forbidden is not None:
        try:
            forbidden_bytes = forbidden.encode("utf-8")
        except UnicodeError:
            forbidden_bytes = b""
        if forbidden_bytes and forbidden_bytes in payload:
            _closed("TOKEN_REJECTED")
    try:
        text = payload.decode("utf-8")
    except UnicodeError:
        _closed("FRAME_INVALID")
    if forbidden and forbidden in text:
        _closed("TOKEN_REJECTED")
    try:
        document = json.loads(
            text,
            object_pairs_hook=_pairs,
            parse_constant=_reject_nonfinite,
            parse_float=_reject_nonfinite,
        )
    except AcpContinuingAuthorityContractError as error:
        error.__context__ = None
        error.__cause__ = None
        error.__suppress_context__ = True
        raise
    except (UnicodeError, json.JSONDecodeError, ValueError, RecursionError):
        _closed("FRAME_INVALID")
    if not isinstance(document, dict):
        _closed("TYPE_INVALID")
    _walk(document, 0, forbidden)
    _exact_keys(document, REQUEST_KEYS)
    phase = document["phase"]
    schema = document["schema"]
    if type(schema) is not str or schema != SCHEMA or type(phase) is not str or phase not in PHASES:
        _closed("TYPE_INVALID")
    identity = document["original_identity"]
    correlation = document["child_correlation"]
    if not isinstance(identity, dict) or not isinstance(correlation, dict):
        raise AcpContinuingAuthorityContractError("TYPE_INVALID")
    _exact_keys(identity, IDENTITY_KEYS)
    _exact_keys(correlation, CORRELATION_KEYS)
    parsed = {
        "schema": SCHEMA,
        "phase": document["phase"],
        "invocation_id": _identifier(document["invocation_id"]),
        "raw_tool": _identifier(document["raw_tool"]),
        "argument_digest": _digest(document["argument_digest"]),
        "request_digest": _digest(document["request_digest"]),
        "original_identity": {
            "job_id": _identifier(identity["job_id"]),
            "attempt_id": _identifier(identity["attempt_id"]),
            "worker_id": _identifier(identity["worker_id"]),
            "quota_class": _identifier(identity["quota_class"]),
            "fence_generation": _fence(identity["fence_generation"]),
        },
        "child_correlation": {
            "connection_id": _identifier(correlation["connection_id"]),
            "catalog_digest": _digest(correlation["catalog_digest"]),
            "definition_digest": _digest(correlation["definition_digest"]),
        },
    }
    if not hmac.compare_digest(
        canonical_request_digest(request_correlation_material(parsed)),
        parsed["request_digest"],
    ):
        _closed("DIGEST_MISMATCH")
    return parsed
