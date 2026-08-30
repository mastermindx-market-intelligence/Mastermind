from __future__ import annotations

import socket
import threading
import time
from collections.abc import Callable

import pytest

from common.runtime_diagnostics import (
    build_runtime_diagnostic_event,
    runtime_diagnostic_event_bytes,
)
from integrations.runtime_observability.sidecar import (
    RuntimeDiagnosticSidecar,
)
from integrations.runtime_observability.sinks import (
    BrokenDiagnosticSinkForTests,
    InMemorySink,
)


def packet(*, event_id_factory=None) -> bytes:
    kwargs = {}
    if event_id_factory is not None:
        kwargs["uuid_factory"] = event_id_factory
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
        **kwargs,
    )
    return runtime_diagnostic_event_bytes(event)


def test_processes_valid_packet() -> None:
    sink = InMemorySink()
    sidecar = RuntimeDiagnosticSidecar(sink=sink)

    result = sidecar.process_packet(packet())

    assert result.accepted is True
    assert result.duplicate is False
    assert result.rejection_class is None
    assert result.event_id is not None
    assert result.sink_failures == ()
    assert len(sink.events) == 1
    assert sidecar.counters.accepted == 1
    assert sidecar.counters.rejected == 0


def test_rejects_malformed_packet_without_raising() -> None:
    sink = InMemorySink()
    sidecar = RuntimeDiagnosticSidecar(sink=sink)

    result = sidecar.process_packet(b"not-json")

    assert result.accepted is False
    assert result.duplicate is False
    assert result.rejection_class == "invalid-json"
    assert result.event_id is None
    assert sink.events == []
    assert sidecar.counters.rejected == 1


def test_duplicate_is_suppressed_inside_bounded_window() -> None:
    now = [10.0]
    sink = InMemorySink()
    sidecar = RuntimeDiagnosticSidecar(
        sink=sink,
        monotonic=lambda: now[0],
        dedupe_max_age_seconds=900.0,
        dedupe_max_entries=4,
    )
    raw = packet()

    first = sidecar.process_packet(raw)
    duplicate = sidecar.process_packet(raw)

    assert first.accepted is True
    assert duplicate.accepted is False
    assert duplicate.duplicate is True
    assert duplicate.rejection_class is None
    assert len(sink.events) == 1
    assert sidecar.counters.duplicate == 1


def test_duplicate_expires_by_age_and_restart_has_no_durable_state() -> None:
    now = [10.0]
    raw = packet()
    first_sink = InMemorySink()
    first = RuntimeDiagnosticSidecar(
        sink=first_sink,
        monotonic=lambda: now[0],
        dedupe_max_age_seconds=5.0,
    )
    assert first.process_packet(raw).accepted is True
    now[0] = 16.0
    assert first.process_packet(raw).accepted is True

    restarted_sink = InMemorySink()
    restarted = RuntimeDiagnosticSidecar(
        sink=restarted_sink,
        monotonic=lambda: now[0],
        dedupe_max_age_seconds=5.0,
    )
    assert restarted.process_packet(raw).accepted is True
    assert len(restarted_sink.events) == 1


def test_dedupe_entry_ceiling_evicts_oldest() -> None:
    import uuid

    ids = iter(
        [
            uuid.UUID("00000000-0000-4000-8000-000000000001"),
            uuid.UUID("00000000-0000-4000-8000-000000000002"),
            uuid.UUID("00000000-0000-4000-8000-000000000003"),
        ]
    )
    now = [1.0]
    sidecar = RuntimeDiagnosticSidecar(
        sink=InMemorySink(),
        monotonic=lambda: now[0],
        dedupe_max_entries=2,
        dedupe_max_age_seconds=900.0,
    )
    raws = []
    for index in range(3):
        event_id = next(ids)
        raws.append(packet(event_id_factory=lambda value=event_id: value))
        assert sidecar.process_packet(raws[-1]).accepted is True
        now[0] += 1.0

    # Oldest was evicted, so it is accepted again rather than treated as duplicate.
    assert sidecar.process_packet(raws[0]).accepted is True


def test_sink_failure_is_counted_but_packet_remains_accepted() -> None:
    healthy = InMemorySink()
    sidecar = RuntimeDiagnosticSidecar(
        sink=BrokenDiagnosticSinkForTests(
            healthy_sink=healthy,
            secret="sk-ant-abcdefghijklmnopqrstuvwxyz",
        )
    )

    result = sidecar.process_packet(packet())

    assert result.accepted is True
    assert len(healthy.events) == 1
    assert len(result.sink_failures) == 1
    assert "sk-ant-" not in result.sink_failures[0].message
    assert sidecar.counters.sink_failed == 1


def test_serve_sockets_processes_valid_and_invalid_datagrams() -> None:
    receiver, sender = socket.socketpair(socket.AF_UNIX, socket.SOCK_DGRAM)
    sink = InMemorySink()
    sidecar = RuntimeDiagnosticSidecar(sink=sink)
    stop = threading.Event()
    result_holder: dict[str, object] = {}

    def run() -> None:
        result_holder["counters"] = sidecar.serve_sockets(
            {"worker": receiver},
            stop_requested=stop.is_set,
            poll_seconds=0.01,
        )

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    try:
        sender.send(packet())
        sender.send(b"not-json")
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            if sidecar.counters.accepted == 1 and sidecar.counters.rejected == 1:
                break
            time.sleep(0.01)
        stop.set()
        thread.join(timeout=2.0)

        assert thread.is_alive() is False
        assert len(sink.events) == 1
        assert sidecar.counters.accepted == 1
        assert sidecar.counters.rejected == 1
        assert result_holder["counters"] is sidecar.counters
        assert sink.closed is True
    finally:
        stop.set()
        sender.close()
        receiver.close()


def test_serve_sockets_refuses_wrong_socket_family() -> None:
    tcp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sidecar = RuntimeDiagnosticSidecar(sink=InMemorySink())
    try:
        with pytest.raises(ValueError, match="AF_UNIX/SOCK_DGRAM"):
            sidecar.serve_sockets(
                {"wrong": tcp},
                stop_requested=lambda: True,
            )
    finally:
        tcp.close()


def test_malformed_packet_classes_are_bounded() -> None:
    sidecar = RuntimeDiagnosticSidecar(sink=InMemorySink())
    hostile = [
        b"",
        b"\xff",
        b"[]",
        b'{"schema_version":"bad"}',
        b"x" * 9000,
    ]
    allowed = {
        "oversized",
        "invalid-utf8",
        "invalid-json",
        "duplicate-key",
        "invalid-shape",
        "invalid-schema",
        "invalid-content",
        "invalid-identifier",
        "invalid-dimension",
        "invalid-duration",
        "unknown",
    }
    for raw in hostile:
        result = sidecar.process_packet(raw)
        assert result.accepted is False
        assert result.rejection_class in allowed
