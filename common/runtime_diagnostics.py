"""Failure-isolated runtime diagnostic event contract and producer transport.

This module is deliberately at the bottom of the dependency stack.  Existing
sealed Executive and Worker processes may import it under ``python -I -S -B``.
It owns no lifecycle state, queue, retry, thread, file, logger, exporter, or
network client.  Diagnostics are best-effort derived evidence only.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
import math
import re
import socket
import uuid
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Protocol

from common.redaction import REDACTION, sanitize_external_text

RUNTIME_DIAGNOSTIC_SCHEMA_VERSION = "mastermind.runtime_diagnostic/v1"
MAX_RUNTIME_DIAGNOSTIC_PACKET_BYTES = 8192
MAX_CORRELATION_FIELDS = 12
MAX_DIMENSION_FIELDS = 12
MAX_IDENTIFIER_LENGTH = 128
MAX_EVENT_NAME_LENGTH = 96
MAX_DURATION_MS = 90_000_000.0

SERVICES = frozenset(
    {
        "executive-control",
        "worker-broker",
        "operator-harness",
        "provider-adapter",
        "agent-dialogue",
        "agent-relay",
        "wake",
        "control-room",
        "runtime-observability-sidecar",
        "runtime-observability-collector",
    }
)

EVENT_NAMES = frozenset(
    {
        "diagnostics.canary",
        "service.started",
        "service.stopped",
        "service.restarted",
        "broker.request.started",
        "broker.request.completed",
        "broker.request.refused",
        "broker.request.interrupted",
        "harness.session.started",
        "harness.session.resumed",
        "harness.session.stopped",
        "harness.session.cancelled",
        "harness.turn.started",
        "harness.turn.completed",
        "harness.turn.interrupted",
        "provider.turn.started",
        "provider.turn.completed",
        "provider.turn.failed",
        "result.collection.started",
        "result.collection.completed",
        "result.collection.refused",
        "dialogue.projection.started",
        "dialogue.projection.completed",
        "dialogue.projection.failed",
        "relay.delivery.started",
        "relay.delivery.completed",
        "relay.delivery.failed",
        "wake.delivery.started",
        "wake.delivery.completed",
        "wake.delivery.failed",
        "collector.export.failed",
        "collector.export.recovered",
    }
)

SIGNALS = frozenset({"POINT", "DURATION"})
OUTCOMES = frozenset(
    {
        "STARTED",
        "SUCCEEDED",
        "FAILED",
        "CANCELLED",
        "REFUSED",
        "UNAVAILABLE",
        "UNKNOWN",
    }
)

CORRELATION_PREFIXES: dict[str, tuple[str, ...]] = {
    "root_job_id": ("root-job:",),
    "job_id": ("job:",),
    "attempt_id": ("attempt:",),
    "worker_id": ("worker:",),
    "run_id": ("run:",),
    "logical_operation_id": ("logical-operation:",),
    "operation_id": ("operation:", "ohfw-op:"),
    "turn_id": ("ohfw-turn:",),
    "process_generation_id": ("process-generation:",),
    "dialogue_parent_id": ("dialogue-parent:",),
    "wake_id": ("wake:",),
    "request_id": ("request:",),
}

DIMENSION_VALUES: dict[str, frozenset[str]] = {
    "phase": frozenset(
        {
            "admission",
            "claim",
            "broker",
            "harness",
            "provider",
            "collection",
            "projection",
            "dialogue",
            "relay",
            "wake",
            "control-room",
            "collector",
        }
    ),
    "operation_class": frozenset(
        {
            "start",
            "status",
            "collect",
            "cancel",
            "validate",
            "autonomy-canary",
            "ohf-validate",
            "ohf-identity",
            "ohf-start",
            "ohf-resume",
            "ohf-begin-turn",
            "ohf-collect-turn",
            "ohf-interrupt",
            "ohf-stop",
            "ohf-cancel",
            "ohf-reconcile",
            "ohf-reconcile-absence",
            "none",
        }
    ),
    "harness": frozenset({"sealed-worker", "operator-harness", "none"}),
    "provider_class": frozenset(
        {
            "codex",
            "claude",
            "cursor",
            "grok",
            "glm",
            "qwen",
            "other-reviewed",
            "none",
        }
    ),
    "transport": frozenset(
        {
            "unix-datagram",
            "unix-stream",
            "otlp-http",
            "otlp-grpc",
            "https",
            "slack",
            "none",
        }
    ),
    "error_class": frozenset(
        {
            "none",
            "validation",
            "authorization",
            "capacity",
            "timeout",
            "rate-limit",
            "authentication",
            "transport",
            "provider",
            "process",
            "protocol",
            "result",
            "projection",
            "storage",
            "resource",
            "unknown",
        }
    ),
    "host_role": frozenset(
        {"control", "worker", "relay", "diagnostics", "mixed-reviewed", "unknown"}
    ),
    "environment": frozenset({"test", "canary", "production", "development"}),
    "deployment_channel": frozenset(
        {"protected", "candidate", "disposable", "unknown"}
    ),
    "evidence_source": frozenset(
        {
            "runtime-emitter",
            "sidecar",
            "alloy",
            "launchd-log",
            "host-metric",
            "backend-query",
        }
    ),
    "result_class": frozenset(
        {
            "none",
            "completed",
            "failed",
            "cancelled",
            "refused",
            "effect-unknown",
            "unavailable",
            "unknown",
        }
    ),
    "availability": frozenset(
        {
            "observed",
            "rejected",
            "dropped",
            "unavailable",
            "stale",
            "absent",
            "unknown",
        }
    ),
}

_CONTROL_CHARS_RE = re.compile(r"[\x00-\x1f\x7f-\x9f]")
_ID_TAIL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,111}$")
_JWT_SHAPE_RE = re.compile(
    r"^eyJ[0-9A-Za-z+/=_-]{4,}\.[0-9A-Za-z+/=_-]{4,}"
    r"(?:\.[0-9A-Za-z+/=_-]*)?$"
)
_KNOWN_CREDENTIAL_PREFIXES = (
    "sb_secret_",
    "sb_publishable_",
    "sbp_",
    "sk-ant-",
    "sk-",
    "github_pat_",
    "ghp_",
    "gho_",
    "ghs_",
)


class RuntimeDiagnosticValidationError(ValueError):
    """A runtime diagnostic event violates the closed source-safe contract."""


@dataclasses.dataclass(frozen=True)
class RuntimeDiagnosticEvent:
    """One immutable bounded diagnostic observation."""

    schema_version: str
    event_id: str
    observed_at: str
    service: str
    event_name: str
    signal: str
    outcome: str
    correlation: Mapping[str, str]
    dimensions: Mapping[str, str]
    duration_ms: float | None = None

    def to_dict(self) -> dict[str, object]:
        document: dict[str, object] = {
            "schema_version": self.schema_version,
            "event_id": self.event_id,
            "observed_at": self.observed_at,
            "service": self.service,
            "event_name": self.event_name,
            "signal": self.signal,
            "outcome": self.outcome,
            "correlation": dict(sorted(self.correlation.items())),
            "dimensions": dict(sorted(self.dimensions.items())),
        }
        if self.duration_ms is not None:
            document["duration_ms"] = self.duration_ms
        return document


def _canonical_utc_timestamp(value: dt.datetime) -> str:
    if not isinstance(value, dt.datetime):
        raise RuntimeDiagnosticValidationError("observed_at must be a datetime")
    if value.tzinfo is None or value.utcoffset() != dt.timedelta(0):
        raise RuntimeDiagnosticValidationError(
            "observed_at must be an aware UTC timestamp"
        )
    return value.isoformat(timespec="microseconds")


def _validate_event_id(value: object) -> str:
    if not isinstance(value, str):
        raise RuntimeDiagnosticValidationError(
            "event_id must be a canonical lowercase UUID v4"
        )
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError) as exc:
        raise RuntimeDiagnosticValidationError(
            "event_id must be a canonical lowercase UUID v4"
        ) from exc
    if parsed.version != 4 or str(parsed) != value:
        raise RuntimeDiagnosticValidationError(
            "event_id must be a canonical lowercase UUID v4"
        )
    return value


def _validate_observed_at(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise RuntimeDiagnosticValidationError(
            "observed_at must be an aware UTC timestamp"
        )
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RuntimeDiagnosticValidationError(
            "observed_at must be an aware UTC timestamp"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() != dt.timedelta(0):
        raise RuntimeDiagnosticValidationError(
            "observed_at must be an aware UTC timestamp"
        )
    canonical = parsed.isoformat(timespec="microseconds")
    if value not in {canonical, canonical.replace("+00:00", "Z")}:
        raise RuntimeDiagnosticValidationError(
            "observed_at must be a canonical aware UTC timestamp"
        )
    return value


def _contains_known_credential_or_jwt(value: str) -> bool:
    lowered = value.lower()
    if _JWT_SHAPE_RE.fullmatch(value):
        return True
    return any(prefix in lowered for prefix in _KNOWN_CREDENTIAL_PREFIXES)


def _reject_unprefixed_secret_shape(value: str) -> None:
    rendered = sanitize_external_text(
        value,
        include_environment=False,
        limit=0,
    )
    if REDACTION in rendered or rendered != value:
        raise RuntimeDiagnosticValidationError(
            "correlation value is secret-shaped"
        )


def _validate_correlation(value: object) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise RuntimeDiagnosticValidationError("correlation must be an object")
    if len(value) > MAX_CORRELATION_FIELDS:
        raise RuntimeDiagnosticValidationError(
            "correlation exceeds the field-count ceiling"
        )
    result: dict[str, str] = {}
    for key, raw in value.items():
        if not isinstance(key, str) or key not in CORRELATION_PREFIXES:
            raise RuntimeDiagnosticValidationError(
                f"correlation key is not allowed: {key!r}"
            )
        if not isinstance(raw, str) or not raw.strip():
            raise RuntimeDiagnosticValidationError(
                f"correlation identifier is invalid for {key}"
            )
        candidate = raw.strip()
        if candidate != raw:
            raise RuntimeDiagnosticValidationError(
                f"correlation identifier is invalid for {key}"
            )
        if _CONTROL_CHARS_RE.search(candidate):
            raise RuntimeDiagnosticValidationError(
                f"correlation identifier is invalid for {key}"
            )

        matched_prefix = next(
            (
                prefix
                for prefix in CORRELATION_PREFIXES[key]
                if candidate.startswith(prefix)
            ),
            None,
        )
        if matched_prefix is None:
            _reject_unprefixed_secret_shape(candidate)
            raise RuntimeDiagnosticValidationError(
                f"correlation identifier has an invalid prefix for {key}"
            )

        tail = candidate[len(matched_prefix) :]
        if _contains_known_credential_or_jwt(tail):
            raise RuntimeDiagnosticValidationError(
                "correlation value is secret-shaped"
            )
        if len(candidate) > MAX_IDENTIFIER_LENGTH or not _ID_TAIL_RE.fullmatch(tail):
            raise RuntimeDiagnosticValidationError(
                f"correlation identifier is invalid for {key}"
            )
        result[key] = candidate
    return dict(sorted(result.items()))


def _validate_dimensions(value: object) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise RuntimeDiagnosticValidationError("dimensions must be an object")
    if len(value) > MAX_DIMENSION_FIELDS:
        raise RuntimeDiagnosticValidationError(
            "dimensions exceed the field-count ceiling"
        )
    result: dict[str, str] = {}
    for key, raw in value.items():
        if not isinstance(key, str) or key not in DIMENSION_VALUES:
            raise RuntimeDiagnosticValidationError(
                f"dimension key is not allowed: {key!r}"
            )
        if not isinstance(raw, str) or raw not in DIMENSION_VALUES[key]:
            raise RuntimeDiagnosticValidationError(
                f"dimension value is not allowed for {key}"
            )
        result[key] = raw
    return dict(sorted(result.items()))


def validate_runtime_diagnostic_event(event: RuntimeDiagnosticEvent) -> None:
    """Validate one event without mutating or projecting it."""

    if not isinstance(event, RuntimeDiagnosticEvent):
        raise RuntimeDiagnosticValidationError(
            "runtime diagnostic event has an invalid type"
        )
    if event.schema_version != RUNTIME_DIAGNOSTIC_SCHEMA_VERSION:
        raise RuntimeDiagnosticValidationError(
            "runtime diagnostic schema version is unsupported"
        )
    _validate_event_id(event.event_id)
    _validate_observed_at(event.observed_at)

    if event.service not in SERVICES:
        raise RuntimeDiagnosticValidationError("service is not allowed")
    if (
        not isinstance(event.event_name, str)
        or len(event.event_name) > MAX_EVENT_NAME_LENGTH
        or event.event_name not in EVENT_NAMES
    ):
        raise RuntimeDiagnosticValidationError("event_name is not allowed")
    if event.signal not in SIGNALS:
        raise RuntimeDiagnosticValidationError("signal is not allowed")
    if event.outcome not in OUTCOMES:
        raise RuntimeDiagnosticValidationError("outcome is not allowed")

    if event.signal == "DURATION":
        if type(event.duration_ms) not in (int, float):
            raise RuntimeDiagnosticValidationError(
                "DURATION events require duration_ms"
            )
        duration = float(event.duration_ms)
        if not math.isfinite(duration) or not 0.0 <= duration <= MAX_DURATION_MS:
            raise RuntimeDiagnosticValidationError(
                "duration_ms is outside the safe range"
            )
    elif event.duration_ms is not None:
        raise RuntimeDiagnosticValidationError(
            "POINT events cannot carry duration_ms"
        )

    _validate_correlation(event.correlation)
    _validate_dimensions(event.dimensions)


def build_runtime_diagnostic_event(
    *,
    service: str,
    event_name: str,
    signal: str,
    outcome: str,
    correlation: Mapping[str, str] | None = None,
    dimensions: Mapping[str, str] | None = None,
    duration_ms: float | None = None,
    now: Callable[[], dt.datetime] = lambda: dt.datetime.now(dt.timezone.utc),
    uuid_factory: Callable[[], uuid.UUID] = uuid.uuid4,
) -> RuntimeDiagnosticEvent:
    """Build and validate one source-safe event."""

    event = RuntimeDiagnosticEvent(
        schema_version=RUNTIME_DIAGNOSTIC_SCHEMA_VERSION,
        event_id=str(uuid_factory()),
        observed_at=_canonical_utc_timestamp(now()),
        service=service,
        event_name=event_name,
        signal=signal,
        outcome=outcome,
        correlation=dict(correlation or {}),
        dimensions=dict(dimensions or {}),
        duration_ms=duration_ms,
    )
    validate_runtime_diagnostic_event(event)
    return event


def runtime_diagnostic_event_bytes(event: RuntimeDiagnosticEvent) -> bytes:
    """Return the exact compact canonical packet for one valid event."""

    validate_runtime_diagnostic_event(event)
    payload = json.dumps(
        event.to_dict(),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    if len(payload) > MAX_RUNTIME_DIAGNOSTIC_PACKET_BYTES:
        raise RuntimeDiagnosticValidationError(
            "runtime diagnostic packet exceeds the byte ceiling"
        )
    return payload


class RuntimeDiagnosticEmitter(Protocol):
    """Best-effort producer boundary; ``False`` means evidence was not emitted."""

    def emit(self, event: RuntimeDiagnosticEvent) -> bool: ...


class NullRuntimeDiagnosticEmitter:
    """Explicit inert emitter used when diagnostics are disabled."""

    def emit(self, event: RuntimeDiagnosticEvent) -> bool:
        return False


class UnixDatagramRuntimeDiagnosticEmitter:
    """Send one bounded event without blocking, retrying, or persisting."""

    def __init__(
        self,
        socket_path: Path,
        *,
        max_packet_bytes: int = MAX_RUNTIME_DIAGNOSTIC_PACKET_BYTES,
        socket_factory: Callable[[int, int], socket.socket] = socket.socket,
    ) -> None:
        self.socket_path = Path(socket_path)
        self.max_packet_bytes = int(max_packet_bytes)
        self._socket_factory = socket_factory

    def emit(self, event: RuntimeDiagnosticEvent) -> bool:
        try:
            payload = runtime_diagnostic_event_bytes(event)
            if len(payload) > self.max_packet_bytes:
                return False
        except Exception:
            return False

        transport = None
        try:
            transport = self._socket_factory(socket.AF_UNIX, socket.SOCK_DGRAM)
            transport.setblocking(False)
            sent = transport.sendto(payload, str(self.socket_path))
            return sent == len(payload)
        except OSError:
            return False
        finally:
            if transport is not None:
                try:
                    transport.close()
                except OSError:
                    pass


__all__ = [
    "CORRELATION_PREFIXES",
    "DIMENSION_VALUES",
    "EVENT_NAMES",
    "MAX_RUNTIME_DIAGNOSTIC_PACKET_BYTES",
    "NullRuntimeDiagnosticEmitter",
    "RUNTIME_DIAGNOSTIC_SCHEMA_VERSION",
    "RuntimeDiagnosticEmitter",
    "RuntimeDiagnosticEvent",
    "RuntimeDiagnosticValidationError",
    "UnixDatagramRuntimeDiagnosticEmitter",
    "build_runtime_diagnostic_event",
    "runtime_diagnostic_event_bytes",
    "validate_runtime_diagnostic_event",
]
