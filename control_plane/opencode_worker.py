"""Bounded OpenCode result parsing and an explicitly unavailable execution seam.

No production descriptor, executable confinement profile or broker composition
exists for this adapter. Constructor facts are input records, not admission.
Lifecycle methods refuse without launching, signalling, registering or retrying.
The parser uses the JSON event shape observed in installed OpenCode 1.18.31.
"""
from __future__ import annotations

import dataclasses
import json
import math
import re
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from control_plane.worker_adapter import WorkerExecutionAdapter
from control_plane.worker_execution_contract import (
    BinaryAttestation, CancelReceipt, CollectionReceipt, ProcessInspector,
    ValidationReceipt, WorkerLaunchSpec, WorkerProcessRef, WorkerRecoveryBinding,
    WorkerRunStatus,
)

MAX_EVENT_STREAM_BYTES = 32 * 1024 * 1024
MAX_EVENT_LINE_BYTES = 1024 * 1024
MAX_EVENT_COUNT = 100_000
MAX_RESULT_BYTES = 1024 * 1024
MAX_JSON_DEPTH = 32
MAX_ID_BYTES = 128
UNREGISTERED_ADAPTER_ID = "opencode-free-cli"
MISSING_COMPOSITION_FIELDS = (
    "reviewed_execution_profile",
    "executable_os_confinement_binding",
    "reviewed_worker_descriptor",
    "worker_broker_factory",
    "canonical_worker_quota_registration",
    "enrolled_remote_host",
    "fresh_capacity_admission",
)


class OpenCodeResultError(ValueError):
    """Closed parser refusal; diagnostics never include a rejected payload."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class OpenCodeLifecycleUnavailable(RuntimeError):
    """Unavailable execution is not a successful or settled provider result."""

    def __init__(self, *, effect: str) -> None:
        self.code = "OPENCODE_EXECUTION_COMPOSITION_UNAVAILABLE"
        self.effect = effect
        super().__init__(self.code)


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


@dataclasses.dataclass(frozen=True)
class OpenCodeParsedResult:
    structured_output: Mapping[str, Any]
    provider_session_id: str
    provider_reported_usage: Mapping[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(self, "structured_output", _freeze(self.structured_output))
        object.__setattr__(self, "provider_reported_usage", _freeze(self.provider_reported_usage))


@dataclasses.dataclass(frozen=True)
class OpenCodeWorkerConfiguration:
    """Explicit owner inputs only; no canonical profile is invented here."""

    binary: BinaryAttestation
    provider_home: Path
    exact_model: str
    execution_profile_id: str | None = None
    execution_profile_digest: str | None = None

    def __post_init__(self) -> None:
        if type(self.binary) is not BinaryAttestation:
            raise ValueError("OPENCODE_BINARY_RECORD_REQUIRED")
        if not Path(self.binary.real_path).is_absolute():
            raise ValueError("OPENCODE_BINARY_PATH_INVALID")
        if not isinstance(self.provider_home, Path) or not self.provider_home.is_absolute():
            raise ValueError("OPENCODE_PROVIDER_HOME_INVALID")
        if self.exact_model != "opencode/mimo-v2.5-free":
            raise ValueError("OPENCODE_EXACT_MODEL_UNSUPPORTED")
        if (self.execution_profile_id is None) != (self.execution_profile_digest is None):
            raise ValueError("OPENCODE_PROFILE_REFERENCE_INCOMPLETE")
        if self.execution_profile_id is not None:
            if (type(self.execution_profile_id) is not str
                    or re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,127}", self.execution_profile_id) is None
                    or type(self.execution_profile_digest) is not str
                    or re.fullmatch(r"[0-9a-f]{64}", self.execution_profile_digest) is None):
                raise ValueError("OPENCODE_PROFILE_REFERENCE_INVALID")


class OpenCodeWorkerAdapter:
    """Frozen constructor/lifecycle contract, deliberately unavailable to run.

    A separately reviewed validation adapter is retained as an owner dependency;
    it does not establish confinement for an OpenCode process. No method invokes
    it while the execution composition remains unavailable.
    """

    adapter_id = UNREGISTERED_ADAPTER_ID

    def __init__(self, configuration: OpenCodeWorkerConfiguration, *,
                 validation_adapter: WorkerExecutionAdapter | None = None,
                 inspector: ProcessInspector | None = None) -> None:
        if type(configuration) is not OpenCodeWorkerConfiguration:
            raise ValueError("OPENCODE_CONFIGURATION_REQUIRED")
        self.configuration = configuration
        self.validation_adapter = validation_adapter
        self.inspector = inspector

    @property
    def missing_composition_fields(self) -> tuple[str, ...]:
        return MISSING_COMPOSITION_FIELDS

    async def start(self, spec: WorkerLaunchSpec) -> WorkerProcessRef:
        raise OpenCodeLifecycleUnavailable(effect="NO_EFFECT")

    async def status(self, ref: WorkerProcessRef) -> WorkerRunStatus:
        raise OpenCodeLifecycleUnavailable(effect="EFFECT_UNKNOWN")

    async def collect_result(self, ref: WorkerProcessRef) -> CollectionReceipt:
        raise OpenCodeLifecycleUnavailable(effect="EFFECT_UNKNOWN")

    async def cancel(self, ref: WorkerProcessRef, reason: str) -> CancelReceipt:
        raise OpenCodeLifecycleUnavailable(effect="EFFECT_UNKNOWN")

    def reattach(self, spec: WorkerLaunchSpec, binding: WorkerRecoveryBinding) -> WorkerProcessRef:
        raise OpenCodeLifecycleUnavailable(effect="EFFECT_UNKNOWN")

    async def run_validation_argv(self, spec: WorkerLaunchSpec, argv: Sequence[str], *,
                                  timeout_seconds: float = 300.0) -> ValidationReceipt:
        raise OpenCodeLifecycleUnavailable(effect="NO_EFFECT")


# BEGIN PARSER IMPLEMENTATION — bounded worker may replace this region only.
def _refuse(code: str) -> None:
    raise OpenCodeResultError(code)


def _json_object(text: str) -> dict[str, Any]:
    # Bound nesting before invoking the recursive stdlib decoder. Brackets in
    # strings do not contribute to depth; syntax itself remains json's job.
    depth = 0
    quoted = escaped = False
    for char in text:
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char in "[{":
            depth += 1
            if depth > MAX_JSON_DEPTH:
                _refuse("OPENCODE_JSON_DEPTH")
        elif char in "}]":
            depth -= 1

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                _refuse("OPENCODE_DUPLICATE_KEY")
            result[key] = value
        return result

    def number(value: str) -> float:
        parsed = float(value)
        if not math.isfinite(parsed):
            _refuse("OPENCODE_NONFINITE_NUMBER")
        return parsed

    try:
        value = json.loads(text, object_pairs_hook=pairs, parse_float=number,
                           parse_constant=lambda _: _refuse("OPENCODE_NONFINITE_NUMBER"))
    except OpenCodeResultError:
        raise
    except (ValueError, TypeError, RecursionError, UnicodeError):
        raise OpenCodeResultError("OPENCODE_JSON_INVALID") from None
    if type(value) is not dict:
        _refuse("OPENCODE_OBJECT_REQUIRED")
    return value


def _identifier(value: Any) -> str:
    if (type(value) is not str or len(value) > MAX_ID_BYTES
            or re.fullmatch(r"[A-Za-z0-9_.:-]+", value) is None):
        _refuse("OPENCODE_ID_INVALID")
    return value


def _counter(value: Any) -> bool:
    return type(value) is int and value >= 0


def _usage(part: dict[str, Any]) -> dict[str, Any]:
    result = {}
    if "cost" in part:
        cost = part["cost"]
        if (type(cost) not in (int, float) or cost < 0
                or (type(cost) is float and not math.isfinite(cost))):
            _refuse("OPENCODE_USAGE_INVALID")
        result["cost"] = cost
    if "tokens" in part:
        tokens = part["tokens"]
        if type(tokens) is not dict or set(tokens) - {"total", "input", "output", "reasoning", "cache"}:
            _refuse("OPENCODE_USAGE_INVALID")
        for key, value in tokens.items():
            if key == "cache":
                if (type(value) is not dict or set(value) - {"read", "write"}
                        or not all(_counter(item) for item in value.values())):
                    _refuse("OPENCODE_USAGE_INVALID")
            elif not _counter(value):
                _refuse("OPENCODE_USAGE_INVALID")
        result["tokens"] = tokens
    return result


def parse_opencode_result(raw: bytes) -> OpenCodeParsedResult:
    """Parse completed final-step JSON, without attesting execution or usage."""
    if type(raw) is not bytes or not raw or len(raw) > MAX_EVENT_STREAM_BYTES:
        _refuse("OPENCODE_STREAM_INVALID")
    if not raw.endswith(b"\n"):
        _refuse("OPENCODE_STREAM_TRUNCATED")
    if raw.count(b"\n") > MAX_EVENT_COUNT:
        _refuse("OPENCODE_EVENT_LIMIT")
    session = message = None
    completed = False
    text_parts: list[str] = []
    text_size = 0
    steps: list[dict[str, Any]] = []
    part_types = {"step_start": "step-start", "tool_use": "tool", "text": "text",
                  "reasoning": "reasoning", "step_finish": "step-finish"}
    for line in raw[:-1].split(b"\n"):
        if completed:
            _refuse("OPENCODE_TRAILING_EVENT")
        if not line or len(line) > MAX_EVENT_LINE_BYTES:
            _refuse("OPENCODE_LINE_INVALID")
        try:
            event = _json_object(line.decode("utf-8"))
        except UnicodeError:
            raise OpenCodeResultError("OPENCODE_UTF8_INVALID") from None
        kind = event.get("type")
        if type(kind) is not str or kind not in (*part_types, "error"):
            _refuse("OPENCODE_EVENT_UNKNOWN")
        event_session = _identifier(event.get("sessionID"))
        if session is not None and event_session != session:
            _refuse("OPENCODE_SESSION_MISMATCH")
        session = event_session
        if not _counter(event.get("timestamp")):
            _refuse("OPENCODE_TIMESTAMP_INVALID")
        if kind == "error":
            _refuse("OPENCODE_PROVIDER_ERROR")
        part = event.get("part")
        if type(part) is not dict or part.get("type") != part_types[kind]:
            _refuse("OPENCODE_PART_INVALID")
        _identifier(part.get("id"))
        part_message = _identifier(part.get("messageID"))
        if "sessionID" in part and part["sessionID"] != session:
            _refuse("OPENCODE_SESSION_MISMATCH")
        if kind == "step_start":
            if message is not None:
                _refuse("OPENCODE_STEP_UNFINISHED")
            message = part_message
            text_parts, text_size = [], 0
            continue
        if message is None or part_message != message:
            _refuse("OPENCODE_MESSAGE_MISMATCH")
        if kind == "text":
            text, time = part.get("text"), part.get("time")
            if (type(text) is not str or type(time) is not dict
                    or not _counter(time.get("start")) or not _counter(time.get("end"))
                    or time["end"] < time["start"]):
                _refuse("OPENCODE_TEXT_INCOMPLETE")
            try:
                text_size += len(text.encode("utf-8"))
            except UnicodeError:
                raise OpenCodeResultError("OPENCODE_UTF8_INVALID") from None
            if text_size > MAX_RESULT_BYTES:
                _refuse("OPENCODE_RESULT_LIMIT")
            text_parts.append(text)
        elif kind == "step_finish":
            if part.get("reason") not in ("tool-calls", "stop"):
                _refuse("OPENCODE_FINISH_INVALID")
            steps.append(_usage(part))
            message = None
            completed = part["reason"] == "stop"
    if not completed or not text_parts:
        _refuse("OPENCODE_RESULT_INCOMPLETE")
    output = _json_object("".join(text_parts))
    return OpenCodeParsedResult(output, session, {"steps": steps})
# END PARSER IMPLEMENTATION
