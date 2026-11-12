"""Unprivileged bounded runtime diagnostic sidecar processor."""

from __future__ import annotations

import dataclasses
import selectors
import socket
import time
from collections import OrderedDict
from collections.abc import Callable, Mapping

from common.runtime_diagnostics import MAX_RUNTIME_DIAGNOSTIC_PACKET_BYTES
from integrations.runtime_observability.contract import (
    RuntimeDiagnosticContractError,
    parse_runtime_diagnostic_packet,
)
from integrations.runtime_observability.sinks import (
    CompositeSink,
    DiagnosticSink,
    SinkFailure,
)

_ALLOWED_REJECTION_CLASSES = frozenset(
    {
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
)


@dataclasses.dataclass(frozen=True)
class SidecarProcessResult:
    accepted: bool
    duplicate: bool
    rejection_class: str | None
    event_id: str | None
    sink_failures: tuple[SinkFailure, ...]


@dataclasses.dataclass
class SidecarCounters:
    accepted: int = 0
    rejected: int = 0
    duplicate: int = 0
    sink_failed: int = 0


class RuntimeDiagnosticSidecar:
    """Validate and project datagrams without owning business state."""

    def __init__(
        self,
        *,
        sink: DiagnosticSink,
        monotonic: Callable[[], float] = time.monotonic,
        dedupe_max_entries: int = 4096,
        dedupe_max_age_seconds: float = 900.0,
    ) -> None:
        if type(dedupe_max_entries) is not int or not 1 <= dedupe_max_entries <= 100_000:
            raise ValueError(
                "dedupe_max_entries must be an integer between 1 and 100000"
            )
        if type(dedupe_max_age_seconds) not in (int, float):
            raise ValueError("dedupe_max_age_seconds must be numeric")
        if not 0.001 <= float(dedupe_max_age_seconds) <= 86_400.0:
            raise ValueError(
                "dedupe_max_age_seconds must be between 0.001 and 86400"
            )
        self._sink = sink if isinstance(sink, CompositeSink) else CompositeSink((sink,))
        self._monotonic = monotonic
        self._dedupe_max_entries = dedupe_max_entries
        self._dedupe_max_age_seconds = float(dedupe_max_age_seconds)
        self._seen: OrderedDict[str, float] = OrderedDict()
        self.counters = SidecarCounters()
        self._sink_closed = False

    def _expire_seen(self, now: float) -> None:
        cutoff = now - self._dedupe_max_age_seconds
        while self._seen:
            _event_id, observed = next(iter(self._seen.items()))
            if observed > cutoff:
                break
            self._seen.popitem(last=False)

    def _remember(self, event_id: str, now: float) -> bool:
        self._expire_seen(now)
        if event_id in self._seen:
            return False
        self._seen[event_id] = now
        while len(self._seen) > self._dedupe_max_entries:
            self._seen.popitem(last=False)
        return True

    @staticmethod
    def _rejection_class(error: RuntimeDiagnosticContractError) -> str:
        code = str(getattr(error, "code", "unknown") or "unknown")
        return code if code in _ALLOWED_REJECTION_CLASSES else "unknown"

    def process_packet(self, raw: bytes) -> SidecarProcessResult:
        """Process one packet and contain all ordinary diagnostic defects."""

        try:
            normalized = parse_runtime_diagnostic_packet(raw)
        except RuntimeDiagnosticContractError as exc:
            self.counters.rejected += 1
            return SidecarProcessResult(
                accepted=False,
                duplicate=False,
                rejection_class=self._rejection_class(exc),
                event_id=None,
                sink_failures=(),
            )
        except Exception:
            self.counters.rejected += 1
            return SidecarProcessResult(
                accepted=False,
                duplicate=False,
                rejection_class="unknown",
                event_id=None,
                sink_failures=(),
            )

        event_id = normalized.event.event_id
        now = float(self._monotonic())
        if not self._remember(event_id, now):
            self.counters.duplicate += 1
            return SidecarProcessResult(
                accepted=False,
                duplicate=True,
                rejection_class=None,
                event_id=event_id,
                sink_failures=(),
            )

        self.counters.accepted += 1
        sink_failures = self._sink.emit(normalized)
        self.counters.sink_failed += len(sink_failures)
        return SidecarProcessResult(
            accepted=True,
            duplicate=False,
            rejection_class=None,
            event_id=event_id,
            sink_failures=sink_failures,
        )

    def _close_sink_once(self) -> tuple[SinkFailure, ...]:
        if self._sink_closed:
            return ()
        self._sink_closed = True
        failures = self._sink.close()
        self.counters.sink_failed += len(failures)
        return failures

    def serve_sockets(
        self,
        sockets: Mapping[str, socket.socket],
        *,
        stop_requested: Callable[[], bool],
        selector_factory: Callable[[], selectors.BaseSelector] = selectors.DefaultSelector,
        poll_seconds: float = 0.25,
    ) -> SidecarCounters:
        """Serve fixed activated Unix datagram sockets until asked to stop."""

        if type(poll_seconds) not in (int, float) or not 0.001 <= float(poll_seconds) <= 5.0:
            raise ValueError("poll_seconds must be between 0.001 and 5.0")
        fixed_sockets = tuple(sockets.items())
        if not fixed_sockets:
            raise ValueError("at least one activated socket is required")
        for source, receiver in fixed_sockets:
            if not isinstance(source, str) or not source:
                raise ValueError("socket source names must be nonempty strings")
            socket_kind = int(receiver.type) & 0xF
            if receiver.family != socket.AF_UNIX or socket_kind != socket.SOCK_DGRAM:
                raise ValueError("sidecar sockets must be AF_UNIX/SOCK_DGRAM")

        selector = selector_factory()
        try:
            for source, receiver in fixed_sockets:
                receiver.setblocking(False)
                selector.register(
                    receiver,
                    selectors.EVENT_READ,
                    data=source,
                )

            while not stop_requested():
                ready = selector.select(float(poll_seconds))
                for key, _mask in ready:
                    receiver = key.fileobj
                    try:
                        raw = receiver.recv(MAX_RUNTIME_DIAGNOSTIC_PACKET_BYTES + 1)
                    except BlockingIOError:
                        continue
                    except OSError:
                        self.counters.rejected += 1
                        continue
                    self.process_packet(raw)
            return self.counters
        finally:
            try:
                selector.close()
            finally:
                self._close_sink_once()


__all__ = [
    "RuntimeDiagnosticSidecar",
    "SidecarCounters",
    "SidecarProcessResult",
]
