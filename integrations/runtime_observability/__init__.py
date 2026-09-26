"""Derived runtime diagnostic evidence primitives.

This package owns no Executive, Agent OS, dialogue, Wake, retry, placement, or
organizational state.  It validates and projects optional diagnostic evidence.
"""

from integrations.runtime_observability.contract import (
    DiagnosticMetricPoint,
    DiagnosticTraceCoordinates,
    NormalizedDiagnosticEvent,
    RuntimeDiagnosticContractError,
    parse_runtime_diagnostic_packet,
)
from integrations.runtime_observability.sidecar import (
    RuntimeDiagnosticSidecar,
    SidecarCounters,
    SidecarProcessResult,
)
from integrations.runtime_observability.sinks import (
    CompositeSink,
    DiagnosticSink,
    InMemorySink,
    JsonLineSink,
    SinkFailure,
)

__all__ = [
    "CompositeSink",
    "DiagnosticMetricPoint",
    "DiagnosticSink",
    "DiagnosticTraceCoordinates",
    "InMemorySink",
    "JsonLineSink",
    "NormalizedDiagnosticEvent",
    "RuntimeDiagnosticContractError",
    "RuntimeDiagnosticSidecar",
    "SidecarCounters",
    "SidecarProcessResult",
    "SinkFailure",
    "parse_runtime_diagnostic_packet",
]
