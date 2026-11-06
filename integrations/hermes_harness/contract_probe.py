"""H24-01 source-only selected-child protocol conformance probe.

This diagnostic calls only explicitly injected fixture transports. It is not a
tool, authorizer, broker, registry, retry controller or production composition.
The receiving Executive owner retains all claims and original-command facts.
No file, socket, credential, clock, Runtime or process is opened by this module.
"""
from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import math
import re
from dataclasses import dataclass, field
from typing import Any, Callable

from control_plane.coo_principal_envelope import PrincipalAdmissionContext
from control_plane.executive_runtime import AttemptStatus, JobStatus
from integrations.hermes_delegate.executive import (
    ExecutiveChildSelection, ExecutiveSelectedChild, _selected_child_valid,
)
from integrations.hermes_delegate.schema import (
    COMMAND_RE, SELECTED_CHILD_FIELDS, SHA_RE, SubmissionError, parse_selected_child,
)
from integrations.hermes_harness import native_tool_registration as native_registration
from integrations.hermes_harness.native_tool_registration import (
    SELECTED_CHILD_SCHEMA, SELECTED_CHILD_STATES, TOOL_NAME,
)
from integrations.hermes_runtime.constants import PINNED_UPSTREAM_SHA
from integrations.hermes_runtime.native_session_control import validate_target
from integrations.mastermind_executive_app.gateway import (
    CeoIngressResponse, MAX_REQUEST_BYTES, MAX_RESPONSE_BYTES,
    TRANSPORT_NOT_SENT, TRANSPORT_SENT_OK,
)

CONTRACT_BASE_SHA = "b54cb10e4abdd3766c62d4088f6a576ecfe80437"
# Digest of the actual C28 NATIVE_TOOL_SCHEMA at CONTRACT_BASE_SHA, canonical JSON.
TOOL_CATALOG_SHA256 = "bb2ed3a7c5a00f3af5bc9f5ea8605eb6e481f40afbbaee277bb98059f47bbe36"
REPORT_SCHEMA = "mastermind.hermes_h24.contract_probe/v1"
_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_REQUIRED = frozenset({
    "schema", "state", "reason", "command_id", "job_id", "attempt_id",
    "attempt_status", "job_status", "live_submit",
})
_OPTIONAL = frozenset({
    "root_job_id", "orchestration_role", "attempt_number", "result_status",
    "role", "operation_key", "session_ref", "result_envelope_digest",
    "terminal_evidence_digest",
})
_NO_ATTEMPT = frozenset({"NOT_CLAIMED", "REFUSED", "EFFECT_UNKNOWN", "UNAVAILABLE"})
_UNCERTAIN = frozenset({"EFFECT_UNKNOWN", "UNAVAILABLE"})
_RESULT_FIELDS = (
    "result_status", "role", "operation_key", "session_ref",
    "result_envelope_digest", "terminal_evidence_digest",
)
_TERMINAL_STATES = frozenset({"COMPLETED", "FAILED", "CANCELLED", "RATE_LIMITED"})
_REASONS = frozenset({
    "JSON_COMPLEXITY", "JSON_KEY_TYPE", "JSON_TOO_LARGE", "JSON_UNICODE",
    "JSON_NONFINITE", "JSON_VALUE_TYPE", "JSON_DUPLICATE_KEY", "JSON_INVALID",
    "JSON_OBJECT_REQUIRED", "SOURCE_GENERATION_INVALID", "NATIVE_TARGET_INVALID",
    "HOST_FIXTURE_INVALID", "SELECTED_CHILD_INVALID", "SOURCE_PIN_MISMATCH",
    "HOST_OBSERVATION_INVALID", "HOST_UNAUTHENTICATED", "REGISTRATION_LEASE_STALE",
    "NATIVE_SESSION_STALE", "PRINCIPAL_CONTEXT_CHANGED", "TARGET_DIGEST_MISMATCH",
    "SOURCE_GENERATION_CHANGED", "ADMISSION_CLOSED", "ENVELOPE_FIELDS",
    "ENVELOPE_SCHEMA", "ENVELOPE_STATE", "ORIGINAL_COMMAND_MISMATCH",
    "ORIGINAL_ROOT_MISMATCH", "ORIGINAL_ORDINAL_MISMATCH", "ATTEMPT_INVALID",
    "EFFECT_INDICATOR_INVALID", "RUNTIME_STATUS_INVALID", "RESULT_DIGEST_INVALID",
    "ENVELOPE_VALUE_INVALID", "ORIGINAL_ATTEMPT_MISMATCH", "ORIGINAL_RESULT_MISMATCH",
    "ORIGINAL_STATE_MISMATCH", "TERMINAL_RESULT_INVALID", "PROBE_FIXTURE_INVALID",
    "TOOL_NAME_MISMATCH", "REQUEST_FIELDS", "REQUEST_SCALAR_TYPE",
    "TRANSPORT_RESULT_UNCERTAIN", "SYNCHRONOUS_RESULT_REQUIRED",
    "ARGUMENTS_NOT_OBJECT", "UNKNOWN_ACTION", "UNKNOWN_FIELD", "COMMAND_INVALID",
})


class ProbeViolation(ValueError):
    """Closed diagnostic code; never exposes a transport exception or authority."""

    def __init__(self, code: str):
        self.code = code if type(code) is str and code in _REASONS else "CONTRACT_INVALID"
        super().__init__(self.code)


def _reason(exc: Exception) -> str:
    code = getattr(exc, "code", getattr(exc, "reason", None))
    return code if type(code) is str and code in _REASONS else "CONTRACT_INVALID"


def _sync_result(value: Any) -> Any:
    if inspect.isawaitable(value):
        if inspect.iscoroutine(value):
            value.close()
        raise ProbeViolation("SYNCHRONOUS_RESULT_REQUIRED")
    return value


def _text(value: Any, limit: int = 256) -> bool:
    return (
        type(value) is str and 0 < len(value) <= limit
        and not any(ord(c) < 32 or 127 <= ord(c) <= 159 or 0xD800 <= ord(c) <= 0xDFFF
                    for c in value)
    )


def _digest(value: Any) -> bool:
    return type(value) is str and SHA_RE.fullmatch(value) is not None


def _tree(value: Any, depth: int = 0, budget: list[int] | None = None,
          string_limit: int = MAX_RESPONSE_BYTES) -> None:
    """Reject coercible Python values, non-finite numbers and oversized trees."""
    if budget is None:
        budget = [4096]
    budget[0] -= 1
    if budget[0] < 0 or depth > 32:
        raise ProbeViolation("JSON_COMPLEXITY")
    kind = type(value)
    if kind is dict:
        for key, child in value.items():
            if type(key) is not str:
                raise ProbeViolation("JSON_KEY_TYPE")
            _tree(key, depth + 1, budget, string_limit)
            _tree(child, depth + 1, budget, string_limit)
    elif kind is list:
        for child in value:
            _tree(child, depth + 1, budget, string_limit)
    elif kind is str:
        if len(value) > string_limit:
            raise ProbeViolation("JSON_TOO_LARGE")
        if any(0xD800 <= ord(c) <= 0xDFFF for c in value):
            raise ProbeViolation("JSON_UNICODE")
    elif kind is float:
        if not math.isfinite(value):
            raise ProbeViolation("JSON_NONFINITE")
    elif kind not in (int, bool, type(None)):
        raise ProbeViolation("JSON_VALUE_TYPE")


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ProbeViolation("JSON_DUPLICATE_KEY")
        result[key] = value
    return result


def _constant(_: str) -> None:
    raise ProbeViolation("JSON_NONFINITE")


def canonical_json(value: Any) -> str:
    _tree(value)
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError, OverflowError, RecursionError):
        raise ProbeViolation("JSON_INVALID") from None


def strict_object(raw: Any, *, limit: int) -> dict[str, Any]:
    """Detach exact JSON; object order is irrelevant, duplicate keys never are."""
    try:
        if type(raw) in (str, bytes):
            if len(raw) > limit:
                raise ProbeViolation("JSON_TOO_LARGE")
            encoded = raw.encode("utf-8") if type(raw) is str else raw
            if len(encoded) > limit:
                raise ProbeViolation("JSON_TOO_LARGE")
            value = json.loads(encoded.decode("utf-8"), object_pairs_hook=_pairs,
                               parse_constant=_constant)
        elif type(raw) is dict:
            value = raw
        else:
            raise ProbeViolation("JSON_OBJECT_REQUIRED")
        _tree(value, string_limit=limit)
        if type(value) is not dict:
            raise ProbeViolation("JSON_OBJECT_REQUIRED")
        encoded = canonical_json(value).encode("utf-8")
        if len(encoded) > limit:
            raise ProbeViolation("JSON_TOO_LARGE")
        # A caller cannot mutate the validated dictionary after this boundary.
        return json.loads(encoded)
    except ProbeViolation:
        raise
    except (UnicodeError, ValueError, TypeError, OverflowError, RecursionError):
        raise ProbeViolation("JSON_INVALID") from None


@dataclass(frozen=True)
class SourceGeneration:
    """Fixture attestation, never a loaded-code or installed-runtime claim."""

    mastermind_sha: str = CONTRACT_BASE_SHA
    catalog_source_sha: str = CONTRACT_BASE_SHA
    upstream_sha: str = PINNED_UPSTREAM_SHA
    catalog_sha256: str = TOOL_CATALOG_SHA256

    def __post_init__(self) -> None:
        if (any(type(v) is not str or _SHA40.fullmatch(v) is None for v in (
                self.mastermind_sha, self.catalog_source_sha, self.upstream_sha))
                or not _digest(self.catalog_sha256)):
            raise ProbeViolation("SOURCE_GENERATION_INVALID")


@dataclass(frozen=True)
class AuthenticatedHostFixture:
    """An already-authenticated test observation, not an authentication API.

    native_target_json uses native_session_control.validate_target verbatim.
    target_digest is supplied by the selected-target owner; H24 neither derives
    C29's target nor invents its digest algorithm. The registration lease is an
    opaque fixture identity. No credential or mutable authority object is stored.
    """

    native_target_json: str
    principal_context: PrincipalAdmissionContext
    target_digest: str
    registration_lease: str
    source: SourceGeneration = field(default_factory=SourceGeneration)
    authenticated: bool = True
    lease_current: bool = True
    admission_open: bool = True

    def __post_init__(self) -> None:
        if type(self.native_target_json) is not str:
            raise ProbeViolation("NATIVE_TARGET_INVALID")
        try:
            target = validate_target(strict_object(self.native_target_json, limit=4096))
        except Exception:
            raise ProbeViolation("NATIVE_TARGET_INVALID") from None
        object.__setattr__(self, "native_target_json", canonical_json(target))
        if (type(self.principal_context) is not PrincipalAdmissionContext
                or type(self.source) is not SourceGeneration
                or not _digest(self.target_digest)
                or not _text(self.registration_lease, 128)
                or any(type(flag) is not bool for flag in (
                    self.authenticated, self.lease_current, self.admission_open))):
            raise ProbeViolation("HOST_FIXTURE_INVALID")


@dataclass(frozen=True)
class ProbeReport:
    outcome: str
    reason: str
    action: str | None
    command_id: str
    job_id: str
    attempt_id: str | None
    transport_called: bool
    modifying_send_possible: bool
    original_readback_called: bool
    envelope_json: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": REPORT_SCHEMA, "evidence": "SOURCE_ONLY",
            "production_execution_proven": False,
            "contract_base_sha": CONTRACT_BASE_SHA,
            "upstream_sha": PINNED_UPSTREAM_SHA,
            "tool_catalog_sha256": TOOL_CATALOG_SHA256,
            "outcome": self.outcome, "reason": self.reason, "action": self.action,
            "command_id": self.command_id, "job_id": self.job_id,
            "attempt_id": self.attempt_id, "transport_called": self.transport_called,
            "modifying_send_possible": self.modifying_send_possible,
            "original_readback_called": self.original_readback_called,
            "envelope": json.loads(self.envelope_json) if self.envelope_json else None,
        }

    def to_json(self) -> str:
        return canonical_json(self.as_dict())


def _child(child: Any) -> None:
    if (type(child) is not ExecutiveSelectedChild
            or type(child.selection) is not ExecutiveChildSelection
            or not _selected_child_valid(child)
            or not _digest(child.selection.plan_digest)
            or COMMAND_RE.fullmatch(child.command_id) is None):
        raise ProbeViolation("SELECTED_CHILD_INVALID")
    selected = child.selection
    if (not all(_text(v, 128) for v in (
            selected.root_job_id, selected.parent_job_id, selected.job_id,
            selected.plan_attempt_id, selected.plan_step_id))
            or (selected.expected_current_attempt_id is not None
                and not _text(selected.expected_current_attempt_id, 128))):
        raise ProbeViolation("SELECTED_CHILD_INVALID")


def _host(expected: AuthenticatedHostFixture, observe: Callable[[], Any],
          *, fresh_submit: bool) -> None:
    # Detect mutable catalog/schema drift without discovering or replacing tools.
    observed_catalog = hashlib.sha256(
        canonical_json(native_registration.NATIVE_TOOL_SCHEMA).encode("utf-8")).hexdigest()
    if expected.source != SourceGeneration() or observed_catalog != TOOL_CATALOG_SHA256:
        raise ProbeViolation("SOURCE_PIN_MISMATCH")
    current = observe()
    if inspect.iscoroutine(current):
        current.close()
    if type(current) is not AuthenticatedHostFixture:
        raise ProbeViolation("HOST_OBSERVATION_INVALID")
    if expected.authenticated is not True or current.authenticated is not True:
        raise ProbeViolation("HOST_UNAUTHENTICATED")
    if (expected.lease_current is not True or current.lease_current is not True
            or current.registration_lease != expected.registration_lease):
        raise ProbeViolation("REGISTRATION_LEASE_STALE")
    if current.native_target_json != expected.native_target_json:
        raise ProbeViolation("NATIVE_SESSION_STALE")
    if current.principal_context != expected.principal_context:
        raise ProbeViolation("PRINCIPAL_CONTEXT_CHANGED")
    if current.target_digest != expected.target_digest:
        raise ProbeViolation("TARGET_DIGEST_MISMATCH")
    if current.source != expected.source:
        raise ProbeViolation("SOURCE_GENERATION_CHANGED")
    if fresh_submit and not current.admission_open:
        raise ProbeViolation("ADMISSION_CLOSED")


def _envelope(raw: Any, child: ExecutiveSelectedChild) -> dict[str, Any]:
    body = strict_object(raw, limit=MAX_RESPONSE_BYTES)
    if not _REQUIRED <= body.keys() or not body.keys() <= _REQUIRED | _OPTIONAL:
        raise ProbeViolation("ENVELOPE_FIELDS")
    if type(body["schema"]) is not str or body["schema"] != SELECTED_CHILD_SCHEMA:
        raise ProbeViolation("ENVELOPE_SCHEMA")
    if (type(body["state"]) is not str or body["state"] not in SELECTED_CHILD_STATES
            or (body["reason"] is not None and not _text(body["reason"]))):
        raise ProbeViolation("ENVELOPE_STATE")
    if (type(body["command_id"]) is not str or body["command_id"] != child.command_id
            or type(body["job_id"]) is not str or body["job_id"] != child.selection.job_id):
        raise ProbeViolation("ORIGINAL_COMMAND_MISMATCH")
    if "root_job_id" in body and (
            type(body["root_job_id"]) is not str
            or body["root_job_id"] != child.selection.root_job_id):
        raise ProbeViolation("ORIGINAL_ROOT_MISMATCH")
    if "attempt_number" in body and (
            type(body["attempt_number"]) is not int
            or body["attempt_number"] != child.attempt_ordinal):
        raise ProbeViolation("ORIGINAL_ORDINAL_MISMATCH")
    attempt = body["attempt_id"]
    if (attempt is not None and not _text(attempt, 128)) or (
            attempt is None and body["state"] not in _NO_ATTEMPT):
        raise ProbeViolation("ATTEMPT_INVALID")
    if body["state"] == "NOT_CLAIMED" and attempt is not None:
        raise ProbeViolation("ATTEMPT_INVALID")
    expected_live = True if attempt is not None else (
        None if body["state"] in _UNCERTAIN else False)
    if body["live_submit"] is not expected_live:
        raise ProbeViolation("EFFECT_INDICATOR_INVALID")
    for name, enum in (("attempt_status", AttemptStatus), ("job_status", JobStatus)):
        value = body[name]
        if value is not None and (type(value) is not str or value not in {v.value for v in enum}):
            raise ProbeViolation("RUNTIME_STATUS_INVALID")
    if attempt is None and body["attempt_status"] is not None:
        raise ProbeViolation("RUNTIME_STATUS_INVALID")
    expected_statuses = {
        "ACTIVE": {AttemptStatus.CLAIMED.value, AttemptStatus.RUNNING.value,
                   AttemptStatus.CHECKPOINTED.value},
        "UNVERIFIED": {AttemptStatus.COMPLETED.value},
        **{state: {AttemptStatus(state).value} for state in
           _TERMINAL_STATES | {"CANCEL_REQUESTED"}},
    }
    if body["state"] in expected_statuses and body["attempt_status"] not in expected_statuses[body["state"]]:
        raise ProbeViolation("RUNTIME_STATUS_INVALID")
    for name in _OPTIONAL - {"root_job_id", "attempt_number"}:
        value = body.get(name)
        if value is not None:
            if name.endswith("_digest"):
                if not _digest(value):
                    raise ProbeViolation("RESULT_DIGEST_INVALID")
            elif not _text(value):
                raise ProbeViolation("ENVELOPE_VALUE_INVALID")
    if body["state"] == "COMPLETED":
        # Actual C17 completion comes only from the sealed terminal-return owner.
        # C28 omits role/operation/session projection, but retains these three.
        if (body["job_status"] != JobStatus.COMPLETED.value
                or body.get("result_status") != "RESULT"
                or not _digest(body.get("result_envelope_digest"))
                or not _digest(body.get("terminal_evidence_digest"))):
            raise ProbeViolation("TERMINAL_RESULT_INVALID")
    elif any(body.get(name) is not None for name in _RESULT_FIELDS):
        raise ProbeViolation("TERMINAL_RESULT_INVALID")
    return body


def _original_matches(body: dict[str, Any], original: dict[str, Any],
                      expected_attempt: str | None) -> None:
    if body["attempt_id"] != original["attempt_id"] or (
            expected_attempt is not None and original["attempt_id"] != expected_attempt):
        raise ProbeViolation("ORIGINAL_ATTEMPT_MISMATCH")
    if (body["attempt_id"] is None or body["state"] in _TERMINAL_STATES) and any(
            body[name] != original[name] for name in ("state", "attempt_status", "job_status")):
        raise ProbeViolation("ORIGINAL_STATE_MISMATCH")
    if body["state"] == "UNVERIFIED" and original["state"] not in {"UNVERIFIED", "COMPLETED"}:
        raise ProbeViolation("ORIGINAL_STATE_MISMATCH")
    # The owner may advance ACTIVE -> COMPLETED between reads. Compare frozen
    # identity and any already-disclosed sealed result, never demand stale state.
    for name in _RESULT_FIELDS:
        value = body.get(name)
        if value is not None and value != original.get(name):
            raise ProbeViolation("ORIGINAL_RESULT_MISMATCH")


@dataclass(frozen=True)
class ContractProbe:
    """One immutable diagnostic binding; no command history or local claim lock.

    read_original is an independent read of the SAME receiving owner's original
    command. A failed call is never followed by an automatic recovery/submit.
    Call run(selected_child_status) explicitly for a later observation.
    """

    selected_child: ExecutiveSelectedChild
    host: AuthenticatedHostFixture
    transport: Any = field(repr=False, compare=False)
    observe_host: Callable[[], AuthenticatedHostFixture] = field(repr=False, compare=False)
    read_original: Callable[[str], Any] = field(repr=False, compare=False)
    original_attempt_id: str | None = None

    def __post_init__(self) -> None:
        _child(self.selected_child)
        if (type(self.host) is not AuthenticatedHostFixture
                or not callable(self.observe_host) or not callable(self.read_original)
                or not callable(getattr(self.transport, "submit_selected_child", None))
                or not callable(getattr(self.transport, "selected_child_status", None))
                or (self.original_attempt_id is not None
                    and not _text(self.original_attempt_id, 128))):
            raise ProbeViolation("PROBE_FIXTURE_INVALID")

    def run(self, arguments: Any, *, tool_name: str = TOOL_NAME) -> ProbeReport:
        action = None
        called = False
        possible = False
        readback = False

        def report(outcome: str, reason: str, body=None) -> ProbeReport:
            return ProbeReport(
                outcome, reason, action, self.selected_child.command_id,
                self.selected_child.selection.job_id,
                body["attempt_id"] if body is not None else self.original_attempt_id,
                called, possible, readback,
                canonical_json(body) if body is not None else None,
            )

        try:
            if type(tool_name) is not str or tool_name != TOOL_NAME:
                raise ProbeViolation("TOOL_NAME_MISMATCH")
            request = strict_object(arguments, limit=MAX_REQUEST_BYTES)
            if set(request) != SELECTED_CHILD_FIELDS:
                raise ProbeViolation("REQUEST_FIELDS")
            # The base parser uses set membership before checking scalar type.
            # H24 refuses malformed values without modifying the C29-owned parser.
            if type(request["action"]) is not str or type(request["command"]) is not str:
                raise ProbeViolation("REQUEST_SCALAR_TYPE")
            request = parse_selected_child(request)
            action = request["action"]
            if request["command"] != self.selected_child.command_id:
                raise ProbeViolation("ORIGINAL_COMMAND_MISMATCH")
            _host(self.host, self.observe_host, fresh_submit=action == "selected_child_submit")
        except (ProbeViolation, SubmissionError) as exc:
            return report("REFUSED", _reason(exc))
        except (Exception, asyncio.CancelledError):
            return report("REFUSED", "PREFLIGHT_UNAVAILABLE")

        # Only this single, explicit invocation can enter the injected transport.
        # Mark uncertainty BEFORE entering: an exception cannot prove non-send.
        called = True
        possible = action == "selected_child_submit"
        try:
            method = (self.transport.submit_selected_child if possible
                      else self.transport.selected_child_status)
            raw = _sync_result(method(self.selected_child.command_id))
            if type(raw) is CeoIngressResponse:
                if type(raw.transport) is not str:
                    raise ProbeViolation("TRANSPORT_RESULT_UNCERTAIN")
                if (raw.transport == TRANSPORT_NOT_SENT and raw.ok is None
                        and raw.result is None and raw.error is None):
                    possible = False
                    return report("REFUSED" if action == "selected_child_submit" else "UNAVAILABLE",
                                  "TRANSPORT_NOT_SENT")
                if (raw.transport != TRANSPORT_SENT_OK or raw.ok is not True
                        or raw.error is not None):
                    raise ProbeViolation("TRANSPORT_RESULT_UNCERTAIN")
                raw = raw.result
            body = _envelope(raw, self.selected_child)
            _host(self.host, self.observe_host, fresh_submit=False)
            readback = True
            original = _envelope(_sync_result(self.read_original(self.selected_child.command_id)),
                                 self.selected_child)
            _original_matches(body, original, self.original_attempt_id)
            _host(self.host, self.observe_host, fresh_submit=False)
            return report("CONFORMANT", "ORIGINAL_COMMAND_OBSERVED", original)
        except (ProbeViolation, SubmissionError) as exc:
            return report("EFFECT_UNKNOWN" if possible else "UNAVAILABLE",
                          _reason(exc))
        except (Exception, asyncio.CancelledError):
            return report("EFFECT_UNKNOWN" if possible else "UNAVAILABLE", "TRANSPORT_OR_READBACK_LOST")
