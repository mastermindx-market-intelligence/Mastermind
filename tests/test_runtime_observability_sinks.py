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
