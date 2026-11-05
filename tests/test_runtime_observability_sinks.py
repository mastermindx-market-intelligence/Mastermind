from __future__ import annotations

import io
import json

from common.runtime_diagnostics import (
    build_runtime_diagnostic_event,
    runtime_diagnostic_event_bytes,
)
from integrations.runtime_observability.contract import (
    parse_runtime_diagnostic_packet,
)
from integrations.runtime_observability.sinks import (
    CompositeSink,
    InMemorySink,
    JsonLineSink,
)


def normalized_event():
    event = build_runtime_diagnostic_event(
        service="worker-broker",
        event_name="diagnostics.canary",
        signal="POINT",
        outcome="SUCCEEDED",
        correlation={"attempt_id": "attempt:attempt-1"},
        dimensions={
            "phase": "broker",
            "environment": "test",
            "evidence_source": "runtime-emitter",
        },
    )
    return parse_runtime_diagnostic_packet(runtime_diagnostic_event_bytes(event))


def test_json_line_sink_emits_one_canonical_line() -> None:
    normalized = normalized_event()
    stream = io.StringIO()
    sink = JsonLineSink(stream)

    result = sink.emit(normalized)

    assert result is None
    lines = stream.getvalue().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0]) == normalized.log_document
    assert stream.getvalue().endswith("\n")


def test_json_line_sink_uses_compact_sorted_json() -> None:
    normalized = normalized_event()
    stream = io.StringIO()
    JsonLineSink(stream).emit(normalized)
    expected = json.dumps(
        normalized.log_document,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ) + "\n"
    assert stream.getvalue() == expected


def test_in_memory_sink_is_bounded_oldest_first() -> None:
    sink = InMemorySink(max_events=2)
    first = normalized_event()
    second = normalized_event()
    third = normalized_event()

    sink.emit(first)
    sink.emit(second)
    sink.emit(third)

    assert sink.events == [second, third]


class BrokenSink:
    def __init__(self, *, fail_emit: bool = True, fail_close: bool = True) -> None:
        self.fail_emit = fail_emit
        self.fail_close = fail_close
        self.emit_calls = 0
        self.close_calls = 0

    def emit(self, event) -> None:
        self.emit_calls += 1
        if self.fail_emit:
            raise RuntimeError("sk-ant-abcdefghijklmnopqrstuvwxyz")

    def close(self) -> None:
        self.close_calls += 1
        if self.fail_close:
            raise RuntimeError("close sk-ant-abcdefghijklmnopqrstuvwxyz")


def test_composite_sink_isolates_one_emit_failure() -> None:
    normalized = normalized_event()
    broken = BrokenSink()
    healthy = InMemorySink()
    composite = CompositeSink((broken, healthy))

    failures = composite.emit(normalized)

    assert healthy.events == [normalized]
    assert broken.emit_calls == 1
    assert len(failures) == 1
    assert failures[0].operation == "emit"
    assert failures[0].sink_class == "BrokenSink"
    assert "sk-ant-" not in failures[0].message
    assert "<redacted>" in failures[0].message


def test_composite_sink_isolates_timeout_and_continues() -> None:
    normalized = normalized_event()
    healthy = InMemorySink()

    class TimeoutSink:
        def emit(self, event) -> None:
            raise TimeoutError("sink timed out with sk-ant-abcdefghijklmnopqrstuvwxyz")

        def close(self) -> None:
            return None

    failures = CompositeSink((TimeoutSink(), healthy)).emit(normalized)

    assert healthy.events == [normalized]
    assert len(failures) == 1
    assert failures[0].operation == "emit"
    assert failures[0].sink_class == "TimeoutSink"
    assert "sk-ant-" not in failures[0].message
    assert "<redacted>" in failures[0].message


def test_composite_sink_isolates_close_failures_and_closes_every_sink() -> None:
    first = BrokenSink()
    second = BrokenSink(fail_emit=False, fail_close=False)
    composite = CompositeSink((first, second))

    failures = composite.close()

    assert first.close_calls == 1
    assert second.close_calls == 1
    assert len(failures) == 1
    assert failures[0].operation == "close"
    assert "sk-ant-" not in failures[0].message


def test_composite_sink_preserves_configured_order() -> None:
    calls: list[str] = []

    class RecordingSink:
        def __init__(self, name: str) -> None:
            self.name = name

        def emit(self, event) -> None:
            calls.append("emit:" + self.name)

        def close(self) -> None:
            calls.append("close:" + self.name)

    composite = CompositeSink(
        (RecordingSink("first"), RecordingSink("second"))
    )
    assert composite.emit(normalized_event()) == ()
    assert composite.close() == ()
    assert calls == [
        "emit:first",
        "emit:second",
        "close:first",
        "close:second",
    ]


class UnrenderableSinkError(Exception):
    def __init__(self) -> None:
        self.render_calls = 0

    def __str__(self) -> str:
        self.render_calls += 1
        raise ValueError("sk-ant-abcdefghijklmnopqrstuvwxyz")


class UnrenderableSink:
    def __init__(self, error: Exception) -> None:
        self.error = error
        self.emit_calls = 0
        self.close_calls = 0

    def emit(self, event) -> None:
        self.emit_calls += 1
        raise self.error

    def close(self) -> None:
        self.close_calls += 1
        raise self.error


def test_composite_sink_contains_unrenderable_emit_failure() -> None:
    event = normalized_event()
    error = UnrenderableSinkError()
    broken = UnrenderableSink(error)
    healthy = InMemorySink()

    failures = CompositeSink((broken, healthy)).emit(event)

    assert healthy.events == [event]
    assert broken.emit_calls == error.render_calls == 1
    assert len(failures) == 1
    assert failures[0].sink_class == "UnrenderableSink"
    assert failures[0].operation == "emit"
    assert failures[0].message == "diagnostic sink failed"


def test_composite_sink_contains_unrenderable_close_failure() -> None:
    error = UnrenderableSinkError()
    broken = UnrenderableSink(error)
    healthy = InMemorySink()

    failures = CompositeSink((broken, healthy)).close()

    assert healthy.closed is True
    assert broken.close_calls == error.render_calls == 1
    assert len(failures) == 1
    assert failures[0].sink_class == "UnrenderableSink"
    assert failures[0].operation == "close"
    assert failures[0].message == "diagnostic sink failed"


class ProcessControlRenderingError(Exception):
    def __str__(self) -> str:
        raise KeyboardInterrupt("process control")


def test_composite_sink_preserves_emit_rendering_process_control() -> None:
    broken = UnrenderableSink(ProcessControlRenderingError())
    healthy = InMemorySink()

    try:
        CompositeSink((broken, healthy)).emit(normalized_event())
    except KeyboardInterrupt:
        pass
    else:
        raise AssertionError("process-control exception was swallowed")

    assert broken.emit_calls == 1
    assert healthy.events == []


def test_composite_sink_preserves_close_rendering_process_control() -> None:
    broken = UnrenderableSink(ProcessControlRenderingError())
    healthy = InMemorySink()

    try:
        CompositeSink((broken, healthy)).close()
    except KeyboardInterrupt:
        pass
    else:
        raise AssertionError("process-control exception was swallowed")

    assert broken.close_calls == 1
    assert healthy.closed is False
