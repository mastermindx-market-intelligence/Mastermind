"""Validate untrusted runtime diagnostic packets and derive evidence projections."""

from __future__ import annotations

import dataclasses
import hashlib
import json
from collections.abc import Mapping

from common.runtime_diagnostics import (
    MAX_RUNTIME_DIAGNOSTIC_PACKET_BYTES,
    RUNTIME_DIAGNOSTIC_SCHEMA_VERSION,
    RuntimeDiagnosticEvent,
    RuntimeDiagnosticValidationError,
    runtime_diagnostic_event_bytes,
    validate_runtime_diagnostic_event,
)

_TRACE_NAMESPACE = b"mastermind.runtime.trace/v1\x00"
_SPAN_NAMESPACE = b"mastermind.runtime.span/v1\x00"
_TRACE_FALLBACK_NAMESPACE = b"mastermind.runtime.trace/v1/fallback\x00"
_SPAN_FALLBACK_NAMESPACE = b"mastermind.runtime.span/v1/fallback\x00"
_TRACE_BASIS_ORDER = (
    "attempt_id",
    "run_id",
    "logical_operation_id",
    "operation_id",
)

_REQUIRED_TOP_LEVEL = frozenset(
    {
        "schema_version",
        "event_id",
        "observed_at",
        "service",
        "event_name",
        "signal",
        "outcome",
        "correlation",
        "dimensions",
    }
)
_OPTIONAL_TOP_LEVEL = frozenset({"duration_ms"})
_ALLOWED_TOP_LEVEL = _REQUIRED_TOP_LEVEL | _OPTIONAL_TOP_LEVEL


class RuntimeDiagnosticContractError(ValueError):
    """An untrusted packet could not be admitted as diagnostic evidence."""

    def __init__(self, message: str, *, code: str = "unknown") -> None:
        super().__init__(message)
        self.code = code


@dataclasses.dataclass(frozen=True)
class DiagnosticTraceCoordinates:
    trace_id: str
    span_id: str
    trace_basis: str


@dataclasses.dataclass(frozen=True)
class DiagnosticMetricPoint:
    name: str
    value: float
    labels: Mapping[str, str]


@dataclasses.dataclass(frozen=True)
class NormalizedDiagnosticEvent:
    event: RuntimeDiagnosticEvent
    event_sha256: str
    trace: DiagnosticTraceCoordinates
    metrics: tuple[DiagnosticMetricPoint, ...]
    log_document: Mapping[str, object]


def _object_without_duplicates(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise RuntimeDiagnosticContractError(
                f"duplicate JSON key: {key}",
                code="duplicate-key",
            )
        result[key] = value
    return result


def _reject_json_constant(value: str) -> object:
    raise RuntimeDiagnosticContractError(
        f"JSON constant is not allowed: {value}",
        code="invalid-json",
    )


def _validation_error(error: RuntimeDiagnosticValidationError) -> RuntimeDiagnosticContractError:
    message = str(error)
    lowered = message.lower()
    if "schema version" in lowered:
        return RuntimeDiagnosticContractError(
            "runtime diagnostic schema is invalid",
            code="invalid-schema",
        )
    if "duration_ms" in lowered or "duration events" in lowered or "point events" in lowered:
        return RuntimeDiagnosticContractError(
            "runtime diagnostic duration is invalid",
            code="invalid-duration",
        )
    if "dimension" in lowered:
        return RuntimeDiagnosticContractError(
            "runtime diagnostic dimension is invalid",
            code="invalid-dimension",
        )
    if "service" in lowered:
        return RuntimeDiagnosticContractError(
            "runtime diagnostic service is invalid",
            code="invalid-content",
        )
    if (
        "identifier" in lowered
        or "event_id" in lowered
        or "correlation" in lowered
        or "prefix" in lowered
    ):
        return RuntimeDiagnosticContractError(
            "runtime diagnostic identifier is invalid",
            code="invalid-identifier",
        )
    return RuntimeDiagnosticContractError(
        "runtime diagnostic content is invalid",
        code="invalid-content",
    )


def _trace_basis(event: RuntimeDiagnosticEvent) -> str:
    for key in _TRACE_BASIS_ORDER:
        value = event.correlation.get(key)
        if value:
            return value
    return event.event_id


def _nonzero_digest_prefix(
    namespace: bytes,
    fallback_namespace: bytes,
    payload: bytes,
    size: int,
) -> bytes:
    selected = hashlib.sha256(namespace + payload).digest()[:size]
    if any(selected):
        return selected
    return hashlib.sha256(fallback_namespace + payload).digest()[:size]


def _derive_trace(event: RuntimeDiagnosticEvent) -> DiagnosticTraceCoordinates:
    basis = _trace_basis(event)
    trace_bytes = _nonzero_digest_prefix(
        _TRACE_NAMESPACE,
        _TRACE_FALLBACK_NAMESPACE,
        basis.encode("utf-8"),
        16,
    )
    span_payload = b"\x00".join(
        (
            trace_bytes,
            event.service.encode("utf-8"),
            event.event_name.encode("utf-8"),
            event.event_id.encode("utf-8"),
        )
    )
    span_bytes = _nonzero_digest_prefix(
        _SPAN_NAMESPACE,
        _SPAN_FALLBACK_NAMESPACE,
        span_payload,
        8,
    )
    return DiagnosticTraceCoordinates(
        trace_id=trace_bytes.hex(),
        span_id=span_bytes.hex(),
        trace_basis=basis,
    )


def _metric_labels(event: RuntimeDiagnosticEvent) -> dict[str, str]:
    labels = {
        "service": event.service,
        "event_name": event.event_name,
        "outcome": event.outcome,
    }
    labels.update(dict(event.dimensions))
    return dict(sorted(labels.items()))


def _metric_projection(
    event: RuntimeDiagnosticEvent,
) -> tuple[DiagnosticMetricPoint, ...]:
    labels = _metric_labels(event)
    points: list[DiagnosticMetricPoint] = [
        DiagnosticMetricPoint(
            name="mastermind_runtime_diagnostic_events_total",
            value=1.0,
            labels=dict(labels),
        )
    ]
    if event.signal == "DURATION" and event.duration_ms is not None:
        points.append(
            DiagnosticMetricPoint(
                name="mastermind_runtime_diagnostic_duration_ms",
                value=float(event.duration_ms),
                labels=dict(labels),
            )
        )
    return tuple(points)


def _log_projection(
    event: RuntimeDiagnosticEvent,
    *,
    event_sha256: str,
    trace: DiagnosticTraceCoordinates,
) -> dict[str, object]:
    document: dict[str, object] = {
        "schema_version": event.schema_version,
        "event_id": event.event_id,
        "event_sha256": event_sha256,
        "observed_at": event.observed_at,
        "service": event.service,
        "event_name": event.event_name,
        "signal": event.signal,
        "outcome": event.outcome,
        "correlation": dict(event.correlation),
        "dimensions": dict(event.dimensions),
        "trace_id": trace.trace_id,
        "span_id": trace.span_id,
        "trace_basis": trace.trace_basis,
        "source": "runtime-diagnostic-sidecar",
        "availability": "OBSERVED",
    }
    if event.duration_ms is not None:
        document["duration_ms"] = float(event.duration_ms)
    return document


def parse_runtime_diagnostic_packet(raw: bytes) -> NormalizedDiagnosticEvent:
    """Parse one bounded untrusted datagram into derived evidence."""

    if not isinstance(raw, bytes):
        raise RuntimeDiagnosticContractError(
            "runtime diagnostic packet must be bytes",
            code="invalid-shape",
        )
    if not raw:
        raise RuntimeDiagnosticContractError(
            "runtime diagnostic packet is empty",
            code="invalid-shape",
        )
    if len(raw) > MAX_RUNTIME_DIAGNOSTIC_PACKET_BYTES:
        raise RuntimeDiagnosticContractError(
            "runtime diagnostic packet exceeds the byte ceiling",
            code="oversized",
        )
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise RuntimeDiagnosticContractError(
            "runtime diagnostic packet is not valid UTF-8",
            code="invalid-utf8",
        ) from exc

    try:
        document = json.loads(
            text,
            object_pairs_hook=_object_without_duplicates,
            parse_constant=_reject_json_constant,
        )
    except RuntimeDiagnosticContractError:
        raise
    except json.JSONDecodeError as exc:
        raise RuntimeDiagnosticContractError(
            "runtime diagnostic packet is not valid JSON",
            code="invalid-json",
        ) from exc

    if not isinstance(document, dict):
        raise RuntimeDiagnosticContractError(
            "runtime diagnostic packet JSON must be an object",
            code="invalid-shape",
        )
    keys = frozenset(document)
    unknown = keys - _ALLOWED_TOP_LEVEL
    missing = _REQUIRED_TOP_LEVEL - keys
    if unknown:
        raise RuntimeDiagnosticContractError(
            "runtime diagnostic packet has unsupported top-level fields",
            code="invalid-shape",
        )
    if missing:
        raise RuntimeDiagnosticContractError(
            "runtime diagnostic packet is missing required top-level fields",
            code="invalid-shape",
        )

    event = RuntimeDiagnosticEvent(
        schema_version=document["schema_version"],
        event_id=document["event_id"],
        observed_at=document["observed_at"],
        service=document["service"],
        event_name=document["event_name"],
        signal=document["signal"],
        outcome=document["outcome"],
        correlation=document["correlation"],
        dimensions=document["dimensions"],
        duration_ms=document.get("duration_ms"),
    )
    try:
        validate_runtime_diagnostic_event(event)
        canonical = runtime_diagnostic_event_bytes(event)
    except RuntimeDiagnosticValidationError as exc:
        raise _validation_error(exc) from exc

    event_sha256 = hashlib.sha256(canonical).hexdigest()
    trace = _derive_trace(event)
    return NormalizedDiagnosticEvent(
        event=event,
        event_sha256=event_sha256,
        trace=trace,
        metrics=_metric_projection(event),
        log_document=_log_projection(
            event,
            event_sha256=event_sha256,
            trace=trace,
        ),
    )


__all__ = [
    "DiagnosticMetricPoint",
    "DiagnosticTraceCoordinates",
    "NormalizedDiagnosticEvent",
    "RuntimeDiagnosticContractError",
    "parse_runtime_diagnostic_packet",
]
