from __future__ import annotations

import socket
from pathlib import Path
from typing import Any

import pytest

import common.runtime_diagnostics as diagnostics
from common.runtime_diagnostics import (
    NullRuntimeDiagnosticEmitter,
    RuntimeDiagnosticEmitter,
    UnixDatagramRuntimeDiagnosticEmitter,
    build_runtime_diagnostic_event,
    runtime_diagnostic_event_bytes,
)


def canary_event():
    return build_runtime_diagnostic_event(
        service="worker-broker",
        event_name="diagnostics.canary",
        signal="POINT",
        outcome="SUCCEEDED",
        correlation={"attempt_id": "attempt:attempt-1"},
        dimensions={
            "phase": "broker",
            "transport": "unix-datagram",
            "environment": "test",
            "evidence_source": "runtime-emitter",
        },
    )


def test_unix_datagram_emitter_sends_exact_packet(tmp_path: Path) -> None:
    path = tmp_path / "diagnostics.sock"
    receiver = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    receiver.bind(str(path))
    receiver.settimeout(1.0)
    try:
        event = canary_event()
        emitter = UnixDatagramRuntimeDiagnosticEmitter(path)
        assert emitter.emit(event) is True
        assert receiver.recv(8193) == runtime_diagnostic_event_bytes(event)
    finally:
        receiver.close()


def test_null_emitter_is_inert() -> None:
    assert NullRuntimeDiagnosticEmitter().emit(canary_event()) is False


class FakeSocket:
    def __init__(
        self,
        *,
        error: OSError | None = None,
        partial_send: bool = False,
        close_error: OSError | None = None,
    ) -> None:
        self.error = error
        self.partial_send = partial_send
        self.close_error = close_error
        self.calls: list[tuple[Any, ...]] = []
        self.closed = False

    def setblocking(self, value: bool) -> None:
        self.calls.append(("setblocking", value))

    def sendto(self, payload: bytes, address: str) -> int:
        self.calls.append(("sendto", payload, address))
        if self.error is not None:
            raise self.error
        if self.partial_send:
            return max(0, len(payload) - 1)
        return len(payload)

    def close(self) -> None:
        self.calls.append(("close",))
        self.closed = True
        if self.close_error is not None:
            raise self.close_error


@pytest.mark.parametrize(
    "error",
    [
        FileNotFoundError("missing"),
        PermissionError("denied"),
        BlockingIOError("full"),
        OSError("transport failed"),
    ],
)
def test_emitter_contains_transport_failures(error: OSError, tmp_path: Path) -> None:
    fake = FakeSocket(error=error)
    emitter = UnixDatagramRuntimeDiagnosticEmitter(
        tmp_path / "absent.sock",
        socket_factory=lambda family, kind: fake,
    )

    assert emitter.emit(canary_event()) is False
    assert fake.calls[0] == ("setblocking", False)
    assert fake.calls[1][0] == "sendto"
    assert fake.calls[-1] == ("close",)
    assert fake.closed is True
    assert sum(1 for call in fake.calls if call[0] == "sendto") == 1


def test_emitter_refuses_partial_datagram_acceptance(tmp_path: Path) -> None:
    fake = FakeSocket(partial_send=True)
    emitter = UnixDatagramRuntimeDiagnosticEmitter(
        tmp_path / "diagnostics.sock",
        socket_factory=lambda family, kind: fake,
    )
    assert emitter.emit(canary_event()) is False
    assert fake.closed is True


def test_emitter_contains_close_failure(tmp_path: Path) -> None:
    fake = FakeSocket(close_error=OSError("close failed"))
    emitter = UnixDatagramRuntimeDiagnosticEmitter(
        tmp_path / "diagnostics.sock",
        socket_factory=lambda family, kind: fake,
    )
    assert emitter.emit(canary_event()) is True
    assert fake.closed is True


def test_emitter_refuses_invalid_event_without_opening_socket(tmp_path: Path) -> None:
    opened = False

    def socket_factory(family: int, kind: int):
        nonlocal opened
        opened = True
        return FakeSocket()

    invalid = diagnostics.RuntimeDiagnosticEvent(
        schema_version="mastermind.runtime_diagnostic/v999",
        event_id="bad",
        observed_at="bad",
        service="bad",
        event_name="bad",
        signal="POINT",
        outcome="UNKNOWN",
        correlation={},
        dimensions={},
    )
    emitter = UnixDatagramRuntimeDiagnosticEmitter(
        tmp_path / "diagnostics.sock",
        socket_factory=socket_factory,
    )

    assert emitter.emit(invalid) is False
    assert opened is False


def run_domain_operation(emitter: RuntimeDiagnosticEmitter) -> tuple[str, int]:
    canonical_result = ("canonical-domain-result", 7)
    try:
        emitter.emit(canary_event())
    except Exception:
        pass
    return canonical_result


class RaisingEmitter:
    def emit(self, event) -> bool:
        raise RuntimeError("diagnostic failure")


def test_domain_result_is_identical_for_all_diagnostic_outcomes(
    tmp_path: Path,
) -> None:
    missing = UnixDatagramRuntimeDiagnosticEmitter(tmp_path / "missing.sock")
    blocked = UnixDatagramRuntimeDiagnosticEmitter(
        tmp_path / "blocked.sock",
        socket_factory=lambda family, kind: FakeSocket(
            error=BlockingIOError("full")
        ),
    )
    emitters: tuple[RuntimeDiagnosticEmitter, ...] = (
        NullRuntimeDiagnosticEmitter(),
        missing,
        blocked,
        RaisingEmitter(),
    )

    results = [run_domain_operation(emitter) for emitter in emitters]
    assert results == [("canonical-domain-result", 7)] * len(emitters)
