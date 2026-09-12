"""Fixed diagnostic sinks with independent failure containment."""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Iterable
from typing import Protocol, TextIO

from common.redaction import sanitize_external_text
from integrations.runtime_observability.contract import NormalizedDiagnosticEvent


class DiagnosticSink(Protocol):
    def emit(self, event: NormalizedDiagnosticEvent) -> object: ...

    def close(self) -> object: ...


@dataclasses.dataclass(frozen=True)
class SinkFailure:
    sink_class: str
    operation: str
    message: str


def _failure(sink: object, operation: str, error: Exception) -> SinkFailure:
    message = sanitize_external_text(
        error,
        include_environment=True,
        limit=160,
    )
    return SinkFailure(
        sink_class=type(sink).__name__[:80] or "unknown",
        operation=operation,
        message=message or "diagnostic sink failed",
    )


class JsonLineSink:
    """Write the normalized source-safe log projection to an injected stream."""

    def __init__(self, stream: TextIO, *, flush: bool = False) -> None:
        self._stream = stream
        self._flush = bool(flush)
        self.closed = False

    def emit(self, event: NormalizedDiagnosticEvent) -> None:
        line = json.dumps(
            event.log_document,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
        self._stream.write(line + "\n")
        if self._flush:
            self._stream.flush()

    def close(self) -> None:
        if self._flush:
            self._stream.flush()
        self.closed = True


class InMemorySink:
    """Bounded disposable/test sink; never a production evidence store."""

    def __init__(self, *, max_events: int = 1024) -> None:
        if type(max_events) is not int or not 1 <= max_events <= 100_000:
            raise ValueError("max_events must be an integer between 1 and 100000")
        self.max_events = max_events
        self.events: list[NormalizedDiagnosticEvent] = []
        self.closed = False

    def emit(self, event: NormalizedDiagnosticEvent) -> None:
        self.events.append(event)
        excess = len(self.events) - self.max_events
        if excess > 0:
            del self.events[:excess]

    def close(self) -> None:
        self.closed = True


class CompositeSink:
    """Invoke a fixed sink set in order while isolating ordinary failures."""

    def __init__(self, sinks: Iterable[DiagnosticSink]) -> None:
        self._sinks = tuple(sinks)

    def emit(
        self,
        event: NormalizedDiagnosticEvent,
    ) -> tuple[SinkFailure, ...]:
        failures: list[SinkFailure] = []
        for sink in self._sinks:
            try:
                sink.emit(event)
            except Exception as exc:
                failures.append(_failure(sink, "emit", exc))
        return tuple(failures)

    def close(self) -> tuple[SinkFailure, ...]:
        failures: list[SinkFailure] = []
        for sink in self._sinks:
            try:
                sink.close()
            except Exception as exc:
                failures.append(_failure(sink, "close", exc))
        return tuple(failures)


__all__ = [
    "CompositeSink",
    "DiagnosticSink",
    "InMemorySink",
    "JsonLineSink",
    "SinkFailure",
]
