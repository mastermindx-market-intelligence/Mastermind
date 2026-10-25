"""Closed request contract for one unarmed ACP currentness observation.

This module parses a bounded request. It does not read Runtime, retain a lease
token, authorize a tool, open a socket, or arm dispatch. The schema is
``mastermind.acp_control_currentness/v1``.
"""
from __future__ import annotations

import json
import math
import re
from typing import Any, Mapping

SCHEMA = "mastermind.acp_control_currentness/v1"
EVIDENCE_SCOPE = "controller_evidence_only"
MAX_REQUEST_BYTES = 4096
MAX_STRING_BYTES = 256
MAX_OBJECT_DEPTH = 1
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


def _walk(value: Any, depth: int) -> None:
    if isinstance(value, dict):
        if depth > MAX_OBJECT_DEPTH:
            raise AcpContinuingAuthorityContractError("NESTING_REFUSED")
        for item in value.values():
            _walk(item, depth + 1)
        return
    if isinstance(value, (list, tuple)):
        raise AcpContinuingAuthorityContractError("COLLECTION_REFUSED")
    if isinstance(value, bool) or value is None:
        return
    if isinstance(value, int):
        return
    if isinstance(value, str):
        if len(value.encode("utf-8")) > MAX_STRING_BYTES:
            raise AcpContinuingAuthorityContractError("LENGTH_EXCEEDED")
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise AcpContinuingAuthorityContractError("NONFINITE")
        raise AcpContinuingAuthorityContractError("TYPE_INVALID")
    raise AcpContinuingAuthorityContractError("TYPE_INVALID")


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


def parse_observation_request(
    raw: bytes,
    *,
    forbidden_exact: str | None = None,
) -> dict[str, Any]:
    """Parse one closed request. ``forbidden_exact`` is rejected, never echoed."""

    if not isinstance(raw, (bytes, bytearray)):
        raise AcpContinuingAuthorityContractError("TYPE_INVALID")
    payload = bytes(raw)
    if len(payload) > MAX_REQUEST_BYTES:
        raise AcpContinuingAuthorityContractError("FRAME_TOO_LARGE")
    if forbidden_exact and forbidden_exact.encode("utf-8") in payload:
        raise AcpContinuingAuthorityContractError("TOKEN_REJECTED")
    try:
        text = payload.decode("utf-8")
    except UnicodeError as exc:
        raise AcpContinuingAuthorityContractError("FRAME_INVALID") from None
    if forbidden_exact and forbidden_exact in text:
        raise AcpContinuingAuthorityContractError("TOKEN_REJECTED")
    try:
        document = json.loads(
            text,
            object_pairs_hook=_pairs,
            parse_constant=_reject_nonfinite,
            parse_float=_reject_nonfinite,
        )
    except AcpContinuingAuthorityContractError:
        raise
    except (UnicodeError, json.JSONDecodeError, ValueError):
        raise AcpContinuingAuthorityContractError("FRAME_INVALID") from None
    if not isinstance(document, dict):
        raise AcpContinuingAuthorityContractError("TYPE_INVALID")
    _walk(document, 0)
    _exact_keys(document, REQUEST_KEYS)
    if document["schema"] != SCHEMA or document["phase"] not in PHASES:
        raise AcpContinuingAuthorityContractError("TYPE_INVALID")
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
    return parsed
