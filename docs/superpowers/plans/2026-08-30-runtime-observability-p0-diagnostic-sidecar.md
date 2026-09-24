# Runtime Observability P0 Diagnostic Sidecar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a real sealed-runtime-safe producer-to-sidecar diagnostic vertical that validates a closed event, emits it over nonblocking Unix datagram transport, derives deterministic trace/log/metric projections, and remains incapable of affecting business lifecycle behavior.

**Architecture:** Existing first-party processes will eventually import a stdlib-only `common.runtime_diagnostics` producer facade. P0 implements that facade and a separate unprivileged sidecar package with injected sinks; it modifies no existing runtime assembly or service. The producer never blocks, retries, logs, or persists. The sidecar owns only bounded process-local dedupe/counters and derived evidence projections.

**Tech Stack:** Python 3.11 standard library, `dataclasses`, `datetime`, `enum`, `hashlib`, `json`, `math`, `os`, `re`, `selectors`, `socket`, `uuid`, `collections.OrderedDict`, pytest.

**Spec:** `docs/superpowers/specs/2026-08-30-mastermind-runtime-observability-fabric-design.md`

## Global Constraints

- Protected implementation basis is the exact accepted F0 head; record its SHA before coding.
- `mastermind.runtime_diagnostic/v1` is the only accepted runtime envelope.
- Maximum encoded event size is 8192 bytes.
- Producers use Python standard library only and remain importable under `python -I -S -B`.
- Producers perform no retry, sleep, thread, queue, file write, log write, DNS, TCP, HTTP, or backend call.
- P0 changes only the exact new paths listed in the F0 architecture.
- P0 adds no third-party dependency and no production service/installer/configuration.
- Correlation IDs may appear in trace/log evidence but never metric labels.
- Unknown fields and secret-bearing values fail closed at validation.
- Diagnostic transport failure returns `False` and never changes the owning operation’s outcome.
- The sidecar owns no Job, Attempt, Worker, Event, retry, queue, session, dialogue, Wake, RuntimeBinding, or organizational state.

---

## File structure

### New producer path

- `common/runtime_diagnostics.py`
  - immutable event type;
  - closed policy constants;
  - builder and validator;
  - canonical serialization;
  - null and Unix-datagram emitter protocols/implementations.

### New sidecar package

- `integrations/runtime_observability/__init__.py`
  - stable public exports only.
- `integrations/runtime_observability/contract.py`
  - untrusted packet parsing;
  - secret-shape checks;
  - deterministic trace/span IDs;
  - structured-log and bounded-metric projection.
- `integrations/runtime_observability/sinks.py`
  - sink protocol;
  - JSON-line, in-memory, and composite sinks.
- `integrations/runtime_observability/sidecar.py`
  - bounded dedupe window;
  - datagram processing;
  - selector-driven receive loop;
  - source-safe self-counters;
  - clean shutdown.
- `scripts/runtime_observability_sidecar.py`
  - narrow disposable/P0 CLI;
  - no arbitrary module/sink loading.

### Tests

- `tests/test_runtime_diagnostics_contract.py`
- `tests/test_runtime_diagnostics_emitter.py`
- `tests/test_runtime_observability_contract.py`
- `tests/test_runtime_observability_sinks.py`
- `tests/test_runtime_observability_sidecar.py`
- `tests/test_runtime_observability_static_fences.py`

---

### Task 1: Freeze the producer policy and immutable event type

**Files:**
- Create: `common/runtime_diagnostics.py`
- Create: `tests/test_runtime_diagnostics_contract.py`

**Interfaces:**
- Produces: `RuntimeDiagnosticEvent`, `RuntimeDiagnosticValidationError`, `build_runtime_diagnostic_event()`, `validate_runtime_diagnostic_event()`, `runtime_diagnostic_event_bytes()`.
- Consumes: Python standard library only.

- [ ] **Step 1: Write the failing exact-valid-event tests**

```python
from __future__ import annotations

import datetime as dt
import json
import uuid

import pytest

from common.runtime_diagnostics import (
    RUNTIME_DIAGNOSTIC_SCHEMA_VERSION,
    RuntimeDiagnosticValidationError,
    build_runtime_diagnostic_event,
    runtime_diagnostic_event_bytes,
    validate_runtime_diagnostic_event,
)


def fixed_now() -> dt.datetime:
    return dt.datetime(2026, 8, 30, 12, 34, 56, 123456, tzinfo=dt.timezone.utc)


def fixed_uuid() -> uuid.UUID:
    return uuid.UUID("4d6b31d2-5810-4f61-9610-416024c0bc19")


def test_builds_exact_valid_point_event() -> None:
    event = build_runtime_diagnostic_event(
        service="worker-broker",
        event_name="diagnostics.canary",
        signal="POINT",
        outcome="SUCCEEDED",
        correlation={"attempt_id": "attempt:abc-123"},
        dimensions={
            "phase": "broker",
            "operation_class": "none",
            "harness": "operator-harness",
            "provider_class": "codex",
            "transport": "unix-datagram",
            "error_class": "none",
            "host_role": "worker",
            "environment": "test",
            "deployment_channel": "disposable",
            "evidence_source": "runtime-emitter",
            "result_class": "completed",
            "availability": "observed",
        },
        now=fixed_now,
        uuid_factory=fixed_uuid,
    )

    assert event.schema_version == RUNTIME_DIAGNOSTIC_SCHEMA_VERSION
    assert event.event_id == str(fixed_uuid())
    assert event.observed_at == "2026-08-30T12:34:56.123456+00:00"
    assert event.duration_ms is None
    validate_runtime_diagnostic_event(event)


def test_canonical_serialization_is_stable() -> None:
    event = build_runtime_diagnostic_event(
        service="worker-broker",
        event_name="diagnostics.canary",
        signal="POINT",
        outcome="SUCCEEDED",
        correlation={"attempt_id": "attempt:abc-123"},
        dimensions={"phase": "broker"},
        now=fixed_now,
        uuid_factory=fixed_uuid,
    )
    raw = runtime_diagnostic_event_bytes(event)
    assert raw == json.dumps(
        event.to_dict(),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    assert len(raw) <= 8192
```

- [ ] **Step 2: Run the tests and verify RED**

Run:

```bash
python -m pytest \
  tests/test_runtime_diagnostics_contract.py::test_builds_exact_valid_point_event \
  tests/test_runtime_diagnostics_contract.py::test_canonical_serialization_is_stable -q
```

Expected: collection fails with `ModuleNotFoundError: No module named 'common.runtime_diagnostics'`.

- [ ] **Step 3: Implement the immutable types and policy constants**

Use this exact public shape:

```python
from __future__ import annotations

import dataclasses
import datetime as dt
import json
import math
import re
import uuid
from collections.abc import Callable, Mapping
from typing import Any, Protocol

RUNTIME_DIAGNOSTIC_SCHEMA_VERSION = "mastermind.runtime_diagnostic/v1"
MAX_RUNTIME_DIAGNOSTIC_PACKET_BYTES = 8192
MAX_CORRELATION_FIELDS = 12
MAX_DIMENSION_FIELDS = 12
MAX_IDENTIFIER_LENGTH = 128
MAX_EVENT_NAME_LENGTH = 96
MAX_DURATION_MS = 90_000_000.0

SERVICES = frozenset({
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
})

SIGNALS = frozenset({"POINT", "DURATION"})
OUTCOMES = frozenset({
    "STARTED", "SUCCEEDED", "FAILED", "CANCELLED",
    "REFUSED", "UNAVAILABLE", "UNKNOWN",
})

@dataclasses.dataclass(frozen=True)
class RuntimeDiagnosticEvent:
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
        result: dict[str, object] = {
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
            result["duration_ms"] = self.duration_ms
        return result

class RuntimeDiagnosticValidationError(ValueError):
    pass
```

Copy the complete closed event-name, correlation-key, prefix, dimension-key, and per-dimension value sets from the design spec into module constants. Do not synthesize values dynamically.

- [ ] **Step 4: Implement builder, validation, and serialization**

Required signatures:

```python
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
) -> RuntimeDiagnosticEvent: ...


def validate_runtime_diagnostic_event(event: RuntimeDiagnosticEvent) -> None: ...


def runtime_diagnostic_event_bytes(event: RuntimeDiagnosticEvent) -> bytes: ...
```

Validation rules:

```python
if event.schema_version != RUNTIME_DIAGNOSTIC_SCHEMA_VERSION:
    raise RuntimeDiagnosticValidationError("runtime diagnostic schema version is unsupported")

parsed_uuid = uuid.UUID(event.event_id)
if parsed_uuid.version != 4 or str(parsed_uuid) != event.event_id:
    raise RuntimeDiagnosticValidationError("event_id must be a canonical lowercase UUID v4")

observed = dt.datetime.fromisoformat(event.observed_at.replace("Z", "+00:00"))
if observed.tzinfo is None or observed.utcoffset() != dt.timedelta(0):
    raise RuntimeDiagnosticValidationError("observed_at must be an aware UTC timestamp")

if event.signal == "DURATION":
    if type(event.duration_ms) not in (int, float):
        raise RuntimeDiagnosticValidationError("DURATION events require duration_ms")
    value = float(event.duration_ms)
    if not math.isfinite(value) or not 0.0 <= value <= MAX_DURATION_MS:
        raise RuntimeDiagnosticValidationError("duration_ms is outside the safe range")
elif event.duration_ms is not None:
    raise RuntimeDiagnosticValidationError("POINT events cannot carry duration_ms")
```

After canonical serialization, refuse packets above the exact ceiling.

- [ ] **Step 5: Run focused tests and verify GREEN**

Run:

```bash
python -m pytest tests/test_runtime_diagnostics_contract.py -q
```

Expected: current Task 1 tests pass.

- [ ] **Step 6: Commit Task 1**

```bash
git add common/runtime_diagnostics.py tests/test_runtime_diagnostics_contract.py
git commit -m "feat(observability): add closed runtime diagnostic event contract"
```

---

### Task 2: Prove hostile shape, content, and cardinality refusal

**Files:**
- Modify: `common/runtime_diagnostics.py`
- Modify: `tests/test_runtime_diagnostics_contract.py`

**Interfaces:**
- Consumes: Task 1 validation functions.
- Produces: exact hostile-input guarantees relied on by emitter and sidecar.

- [ ] **Step 1: Add parameterized hostile tests**

```python
@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("service", "worker-broker-evil", "service is not allowed"),
        ("event_name", "model.authored.event", "event_name is not allowed"),
        ("signal", "SPAN", "signal is not allowed"),
        ("outcome", "RETRIED", "outcome is not allowed"),
    ],
)
def test_refuses_unknown_closed_values(field: str, value: str, message: str) -> None:
    kwargs = {
        "service": "worker-broker",
        "event_name": "diagnostics.canary",
        "signal": "POINT",
        "outcome": "SUCCEEDED",
        "correlation": {},
        "dimensions": {},
        "now": fixed_now,
        "uuid_factory": fixed_uuid,
    }
    kwargs[field] = value
    with pytest.raises(RuntimeDiagnosticValidationError, match=message):
        build_runtime_diagnostic_event(**kwargs)


@pytest.mark.parametrize(
    "secret",
    [
        "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ4In0.signature",
        "sk-ant-abcdefghijklmnopqrstuvwxyz",
        "github_pat_abcdefghijklmnopqrstuvwxyz",
        "a" * 40,
        "AbCdEfGhIjKlMnOpQrStUvWxYz0123456789_-=",
    ],
)
def test_refuses_secret_shaped_unprefixed_values(secret: str) -> None:
    with pytest.raises(RuntimeDiagnosticValidationError, match="secret-shaped"):
        build_runtime_diagnostic_event(
            service="worker-broker",
            event_name="diagnostics.canary",
            signal="POINT",
            outcome="FAILED",
            correlation={"request_id": secret},
            dimensions={},
            now=fixed_now,
            uuid_factory=fixed_uuid,
        )


def test_accepts_prefixed_canonical_identifier_with_long_digest() -> None:
    event = build_runtime_diagnostic_event(
        service="worker-broker",
        event_name="diagnostics.canary",
        signal="POINT",
        outcome="SUCCEEDED",
        correlation={"attempt_id": "attempt:" + "a" * 40},
        dimensions={},
        now=fixed_now,
        uuid_factory=fixed_uuid,
    )
    assert event.correlation["attempt_id"] == "attempt:" + "a" * 40


def test_correlation_and_dimension_key_sets_are_closed() -> None:
    with pytest.raises(RuntimeDiagnosticValidationError, match="correlation key"):
        build_runtime_diagnostic_event(
            service="worker-broker",
            event_name="diagnostics.canary",
            signal="POINT",
            outcome="SUCCEEDED",
            correlation={"prompt": "never"},
            dimensions={},
            now=fixed_now,
            uuid_factory=fixed_uuid,
        )
    with pytest.raises(RuntimeDiagnosticValidationError, match="dimension key"):
        build_runtime_diagnostic_event(
            service="worker-broker",
            event_name="diagnostics.canary",
            signal="POINT",
            outcome="SUCCEEDED",
            correlation={},
            dimensions={"job_id": "job:never-a-label"},
            now=fixed_now,
            uuid_factory=fixed_uuid,
        )
```

Also test:

- more than 12 fields;
- empty/whitespace strings;
- control characters;
- email/path/URL values;
- overlength identifiers;
- bool duration;
- negative, NaN, infinity, and over-ceiling duration;
- POINT with duration and DURATION without duration;
- non-UTC/naive timestamps;
- UUID v1/v5 and uppercase UUID;
- direct dataclass construction followed by validation;
- exact 8192-byte and 8193-byte encoded boundaries.

- [ ] **Step 2: Run new tests and verify RED**

Run:

```bash
python -m pytest tests/test_runtime_diagnostics_contract.py -q
```

Expected: hostile tests fail because Task 1 does not yet implement every shape/content rule.

- [ ] **Step 3: Implement exact safe-identifier validation**

Use per-key prefix policy:

```python
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
```

After an exact allowed prefix, the tail matches:

```python
_ID_TAIL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,111}$")
```

No generic mapping or arbitrary string is accepted. Dimension values are checked against the exact per-key value sets from the spec.

- [ ] **Step 4: Implement secret-shape rejection before length truncation**

Copy the relevant shape expressions from `common.redaction` into private **recognition-only** predicates only if importing private constants is impossible. Do not create a second sanitizer. The validator rejects, rather than redacts, secret-shaped noncanonical strings.

Keep the order:

1. control characters;
2. JWT;
3. known secret prefix;
4. unprefixed long hex;
5. unprefixed long base64url/token;
6. email/path/URL-like content where prohibited;
7. length.

- [ ] **Step 5: Run focused tests and verify GREEN**

```bash
python -m pytest tests/test_runtime_diagnostics_contract.py -q
```

- [ ] **Step 6: Commit Task 2**

```bash
git add common/runtime_diagnostics.py tests/test_runtime_diagnostics_contract.py
git commit -m "test(observability): harden diagnostic content and cardinality bounds"
```

---

### Task 3: Implement the nonblocking Unix datagram emitter

**Files:**
- Modify: `common/runtime_diagnostics.py`
- Create: `tests/test_runtime_diagnostics_emitter.py`

**Interfaces:**
- Consumes: `runtime_diagnostic_event_bytes()`.
- Produces: `RuntimeDiagnosticEmitter`, `NullRuntimeDiagnosticEmitter`, `UnixDatagramRuntimeDiagnosticEmitter`.

- [ ] **Step 1: Write a real disposable-socket success test**

```python
from __future__ import annotations

import socket
from pathlib import Path

from common.runtime_diagnostics import (
    NullRuntimeDiagnosticEmitter,
    UnixDatagramRuntimeDiagnosticEmitter,
    build_runtime_diagnostic_event,
    runtime_diagnostic_event_bytes,
)


def test_unix_datagram_emitter_sends_exact_packet(tmp_path: Path) -> None:
    path = tmp_path / "diagnostics.sock"
    receiver = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    receiver.bind(str(path))
    receiver.settimeout(1.0)
    try:
        event = build_runtime_diagnostic_event(
            service="worker-broker",
            event_name="diagnostics.canary",
            signal="POINT",
            outcome="SUCCEEDED",
            correlation={"attempt_id": "attempt:abc-123"},
            dimensions={"phase": "broker"},
        )
        emitter = UnixDatagramRuntimeDiagnosticEmitter(path)
        assert emitter.emit(event) is True
        assert receiver.recv(8193) == runtime_diagnostic_event_bytes(event)
    finally:
        receiver.close()


def test_null_emitter_is_inert() -> None:
    event = build_runtime_diagnostic_event(
        service="worker-broker",
        event_name="diagnostics.canary",
        signal="POINT",
        outcome="SUCCEEDED",
    )
    assert NullRuntimeDiagnosticEmitter().emit(event) is False
```

- [ ] **Step 2: Write mocked failure-isolation tests**

Patch the module’s socket factory with a fake that records ordering and raises:

```python
class FakeSocket:
    def __init__(self, error: OSError | None = None) -> None:
        self.error = error
        self.calls: list[object] = []
        self.closed = False

    def setblocking(self, value: bool) -> None:
        self.calls.append(("setblocking", value))

    def sendto(self, payload: bytes, address: str) -> int:
        self.calls.append(("sendto", payload, address))
        if self.error is not None:
            raise self.error
        return len(payload)

    def close(self) -> None:
        self.calls.append(("close",))
        self.closed = True
```

Test `FileNotFoundError`, `PermissionError`, `BlockingIOError`, generic `OSError`, and partial-send return. Every case returns `False`, closes, and never retries. Verify `setblocking(False)` precedes `sendto`.

- [ ] **Step 3: Run emitter tests and verify RED**

```bash
python -m pytest tests/test_runtime_diagnostics_emitter.py -q
```

Expected: imports or emitter assertions fail.

- [ ] **Step 4: Implement exact emitter types**

```python
class RuntimeDiagnosticEmitter(Protocol):
    def emit(self, event: RuntimeDiagnosticEvent) -> bool: ...


class NullRuntimeDiagnosticEmitter:
    def emit(self, event: RuntimeDiagnosticEvent) -> bool:
        return False


class UnixDatagramRuntimeDiagnosticEmitter:
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
```

Do not catch `BaseException`; cancellation/termination signals stay process-authoritative. Contain ordinary diagnostic programming/validation/transport errors only.

- [ ] **Step 5: Add static no-side-effect assertions**

Inspect source with `ast` and assert producer module imports none of:

```text
asyncio, concurrent, logging, multiprocessing, requests, httpx,
subprocess, threading, time.sleep, urllib
```

Also assert emitter source contains no loop around `sendto` and no file `open()`.

- [ ] **Step 6: Run focused tests and verify GREEN**

```bash
python -m pytest \
  tests/test_runtime_diagnostics_contract.py \
  tests/test_runtime_diagnostics_emitter.py -q
```

- [ ] **Step 7: Commit Task 3**

```bash
git add common/runtime_diagnostics.py tests/test_runtime_diagnostics_emitter.py
git commit -m "feat(observability): add failure-isolated Unix datagram emitter"
```

---

### Task 4: Parse untrusted packets and derive trace/log/metric projections

**Files:**
- Create: `integrations/runtime_observability/__init__.py`
- Create: `integrations/runtime_observability/contract.py`
- Create: `tests/test_runtime_observability_contract.py`

**Interfaces:**
- Consumes: producer event policy and canonical bytes.
- Produces: `DiagnosticTraceCoordinates`, `DiagnosticMetricPoint`, `NormalizedDiagnosticEvent`, `RuntimeDiagnosticContractError`, `parse_runtime_diagnostic_packet()`.

- [ ] **Step 1: Write valid projection tests**

```python
from __future__ import annotations

import hashlib

from common.runtime_diagnostics import (
    build_runtime_diagnostic_event,
    runtime_diagnostic_event_bytes,
)
from integrations.runtime_observability.contract import (
    parse_runtime_diagnostic_packet,
)


def test_parses_event_and_derives_stable_trace_coordinates() -> None:
    event = build_runtime_diagnostic_event(
        service="worker-broker",
        event_name="broker.request.completed",
        signal="DURATION",
        outcome="SUCCEEDED",
        duration_ms=125.5,
        correlation={
            "job_id": "job:job-1",
            "attempt_id": "attempt:attempt-1",
            "worker_id": "worker:worker-1",
        },
        dimensions={
            "phase": "broker",
            "operation_class": "collect",
            "error_class": "none",
        },
    )
    normalized = parse_runtime_diagnostic_packet(runtime_diagnostic_event_bytes(event))

    assert normalized.event == event
    assert normalized.event_sha256 == hashlib.sha256(
        runtime_diagnostic_event_bytes(event)
    ).hexdigest()
    assert len(normalized.trace.trace_id) == 32
    assert len(normalized.trace.span_id) == 16
    assert normalized.trace.trace_basis == "attempt:attempt-1"
    assert normalized.log_document["correlation"]["job_id"] == "job:job-1"


def test_metric_labels_never_include_correlation_values() -> None:
    event = build_runtime_diagnostic_event(
        service="worker-broker",
        event_name="broker.request.completed",
        signal="DURATION",
        outcome="SUCCEEDED",
        duration_ms=125.5,
        correlation={
            "job_id": "job:SECRET-JOB-VALUE",
            "attempt_id": "attempt:SECRET-ATTEMPT-VALUE",
        },
        dimensions={"phase": "broker"},
    )
    normalized = parse_runtime_diagnostic_packet(runtime_diagnostic_event_bytes(event))
    for point in normalized.metrics:
        serialized = repr(dict(point.labels))
        assert "SECRET-JOB-VALUE" not in serialized
        assert "SECRET-ATTEMPT-VALUE" not in serialized
```

- [ ] **Step 2: Write hostile packet tests**

Test raw bytes for:

- empty packet;
- `8193` bytes;
- invalid UTF-8;
- invalid JSON;
- JSON list/scalar;
- duplicate JSON keys using `object_pairs_hook` refusal;
- unknown field;
- direct secret-shaped payload;
- noncanonical JSON that parses to a valid object;
- caller-supplied `trace_id` or `span_id`;
- bool/NaN duration;
- malformed canonical ID;
- top-level object with repeated key.

The parser may accept noncanonical key ordering because transport does not require producer identity, but the normalized event digest must be over reserialized canonical bytes, not raw attacker bytes.

- [ ] **Step 3: Run contract tests and verify RED**

```bash
python -m pytest tests/test_runtime_observability_contract.py -q
```

- [ ] **Step 4: Implement exact normalized dataclasses**

```python
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
```

- [ ] **Step 5: Implement duplicate-key-safe JSON parsing**

```python
def _object_without_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise RuntimeDiagnosticContractError(f"duplicate JSON key: {key}")
        result[key] = value
    return result
```

Decode strict UTF-8, enforce byte ceiling before decode, use `parse_constant` to reject NaN/Infinity, and require a dict.

Reconstruct `RuntimeDiagnosticEvent` only from the exact allowed keys and call `validate_runtime_diagnostic_event()`.

- [ ] **Step 6: Implement deterministic trace/span projection**

Use the exact namespaces and basis order from the spec:

```python
_TRACE_NAMESPACE = b"mastermind.runtime.trace/v1\x00"
_SPAN_NAMESPACE = b"mastermind.runtime.span/v1\x00"
_TRACE_BASIS_ORDER = (
    "attempt_id", "run_id", "logical_operation_id", "operation_id"
)
```

Derive 16 trace bytes and 8 span bytes. Refuse no caller-provided trace fields because the top-level schema is closed.

- [ ] **Step 7: Implement log and metric projection**

Metrics:

```python
labels = {
    "service": event.service,
    "event_name": event.event_name,
    "outcome": event.outcome,
    **dict(event.dimensions),
}
```

Never merge `event.correlation` into labels. Produce one event counter and, for duration events, one duration point.

The log document contains exact correlation, dimensions, trace IDs, digest, and source, but no raw bytes or parser errors.

- [ ] **Step 8: Run focused tests and verify GREEN**

```bash
python -m pytest \
  tests/test_runtime_diagnostics_contract.py \
  tests/test_runtime_observability_contract.py -q
```

- [ ] **Step 9: Commit Task 4**

```bash
git add integrations/runtime_observability tests/test_runtime_observability_contract.py
git commit -m "feat(observability): normalize diagnostic trace log and metric evidence"
```

---

### Task 5: Implement isolated sinks

**Files:**
- Create: `integrations/runtime_observability/sinks.py`
- Create: `tests/test_runtime_observability_sinks.py`

**Interfaces:**
- Consumes: `NormalizedDiagnosticEvent`.
- Produces: `DiagnosticSink`, `JsonLineSink`, `InMemorySink`, `CompositeSink`, `SinkFailure`.

- [ ] **Step 1: Write sink tests**

```python
import io
import json

from integrations.runtime_observability.sinks import (
    CompositeSink,
    InMemorySink,
    JsonLineSink,
)


def test_json_line_sink_emits_one_canonical_line(normalized_event) -> None:
    stream = io.StringIO()
    sink = JsonLineSink(stream)
    sink.emit(normalized_event)
    lines = stream.getvalue().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0]) == normalized_event.log_document


def test_composite_sink_isolates_one_failure(normalized_event) -> None:
    class BrokenSink:
        def emit(self, event) -> None:
            raise RuntimeError("sk-ant-abcdefghijklmnopqrstuvwxyz")
        def close(self) -> None:
            raise RuntimeError("close failed")

    healthy = InMemorySink()
    composite = CompositeSink((BrokenSink(), healthy))
    failures = composite.emit(normalized_event)
    assert healthy.events == [normalized_event]
    assert len(failures) == 1
    assert "sk-ant-" not in failures[0].message
    assert "<redacted>" in failures[0].message
```

Also test deterministic sink order, close isolation, bounded failure message, and no retry.

- [ ] **Step 2: Run tests and verify RED**

```bash
python -m pytest tests/test_runtime_observability_sinks.py -q
```

- [ ] **Step 3: Implement sink protocol and immutable failure**

```python
class DiagnosticSink(Protocol):
    def emit(self, event: NormalizedDiagnosticEvent) -> object: ...
    def close(self) -> object: ...

@dataclasses.dataclass(frozen=True)
class SinkFailure:
    sink_class: str
    operation: str
    message: str
```

`CompositeSink.emit()` returns `tuple[SinkFailure, ...]`. It uses `sanitize_external_text(..., limit=160)` for caught sink exception text and never raises because one sink failed. It does not catch `BaseException`.

- [ ] **Step 4: Implement `JsonLineSink` and `InMemorySink`**

`JsonLineSink` serializes `normalized.log_document` with sorted keys, compact separators, `ensure_ascii=True`, `allow_nan=False`, adds exactly one newline, flushes only when configured, and never serializes the raw event packet.

`InMemorySink` is a bounded test sink with a constructor ceiling and oldest-first eviction. Mark it clearly test/disposable; production composition must not use it.

- [ ] **Step 5: Run tests and verify GREEN**

```bash
python -m pytest tests/test_runtime_observability_sinks.py -q
```

- [ ] **Step 6: Commit Task 5**

```bash
git add integrations/runtime_observability/sinks.py tests/test_runtime_observability_sinks.py
git commit -m "feat(observability): add isolated diagnostic sinks"
```

---

### Task 6: Build the bounded sidecar processor and datagram loop

**Files:**
- Create: `integrations/runtime_observability/sidecar.py`
- Create: `tests/test_runtime_observability_sidecar.py`

**Interfaces:**
- Consumes: packet parser and fixed sink.
- Produces: `RuntimeDiagnosticSidecar`, `SidecarCounters`, `SidecarProcessResult`.

- [ ] **Step 1: Write single-packet and malformed-packet processor tests**

```python
from integrations.runtime_observability.sidecar import RuntimeDiagnosticSidecar
from integrations.runtime_observability.sinks import InMemorySink


def test_processes_valid_packet(normalized_packet: bytes) -> None:
    sink = InMemorySink()
    sidecar = RuntimeDiagnosticSidecar(sink=sink)
    result = sidecar.process_packet(normalized_packet)
    assert result.accepted is True
    assert result.duplicate is False
    assert result.rejection_class is None
    assert len(sink.events) == 1
    assert sidecar.counters.accepted == 1


def test_rejects_malformed_packet_without_raising() -> None:
    sink = InMemorySink()
    sidecar = RuntimeDiagnosticSidecar(sink=sink)
    result = sidecar.process_packet(b"not-json")
    assert result.accepted is False
    assert result.rejection_class == "invalid-json"
    assert sink.events == []
    assert sidecar.counters.rejected == 1
```

- [ ] **Step 2: Write dedupe-bound tests**

Inject a monotonic clock. Prove:

- same event ID inside 15 minutes is duplicate and not emitted;
- age expiry permits re-observation;
- entry ceiling 4096 evicts oldest deterministically;
- no file/database write occurs;
- restart/new instance has empty dedupe state.

- [ ] **Step 3: Write real socket-loop test**

Create a bound disposable `AF_UNIX/SOCK_DGRAM` receiver socket and pass it to `serve_socket()`. Run the loop in a test thread only; send one valid and one invalid packet, trigger a stop event, and assert clean exit, one accepted event, one rejection, and closed sinks.

The production code itself must not create worker threads. The test may run the blocking loop in a thread to exercise it.

- [ ] **Step 4: Run tests and verify RED**

```bash
python -m pytest tests/test_runtime_observability_sidecar.py -q
```

- [ ] **Step 5: Implement immutable result/counter types**

```python
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
```

Counters are process-local diagnostics only.

- [ ] **Step 6: Implement bounded dedupe**

Use an `OrderedDict[str, float]`, injected monotonic clock, exact ceiling and max age. Evict expired entries before duplicate check, then evict oldest until under ceiling after insert.

- [ ] **Step 7: Implement `process_packet()`**

Classify refusals into a fixed set:

```text
oversized, invalid-utf8, invalid-json, duplicate-key, invalid-shape,
invalid-schema, invalid-content, invalid-identifier, invalid-dimension,
invalid-duration, unknown
```

Do not expose the raw packet or full exception. The result carries only the fixed class and accepted event ID.

- [ ] **Step 8: Implement selector-driven receive loop**

Required signature:

```python
def serve_sockets(
    self,
    sockets: Mapping[str, socket.socket],
    *,
    stop_requested: Callable[[], bool],
    selector_factory: Callable[[], selectors.BaseSelector] = selectors.DefaultSelector,
    poll_seconds: float = 0.25,
) -> SidecarCounters: ...
```

Rules:

- every supplied socket must be `AF_UNIX/SOCK_DGRAM`;
- set receiver sockets nonblocking;
- register each with fixed source name;
- `recv(MAX_PACKET_BYTES + 1)`;
- process all ready datagrams;
- malformed input never exits loop;
- stop check occurs each poll;
- no dynamic socket/path creation;
- close selector in `finally`;
- caller owns activated sockets;
- close sink exactly once at terminal loop exit;
- no business-service callback.

- [ ] **Step 9: Run tests and verify GREEN**

```bash
python -m pytest \
  tests/test_runtime_observability_contract.py \
  tests/test_runtime_observability_sinks.py \
  tests/test_runtime_observability_sidecar.py -q
```

- [ ] **Step 10: Commit Task 6**

```bash
git add integrations/runtime_observability/sidecar.py tests/test_runtime_observability_sidecar.py
git commit -m "feat(observability): add bounded diagnostic sidecar loop"
```

---

### Task 7: Add a narrow disposable CLI and static authority fences

**Files:**
- Create: `scripts/runtime_observability_sidecar.py`
- Create: `tests/test_runtime_observability_static_fences.py`
- Modify: `integrations/runtime_observability/__init__.py`

**Interfaces:**
- Consumes: sidecar and JSON line sink.
- Produces: a test/disposable CLI, not a production service installer.

- [ ] **Step 1: Write CLI argument refusal tests**

The P0 CLI accepts exactly:

```text
--socket-path <absolute disposable path>
--max-events <1..10000>
```

It writes accepted canonical JSON lines to stdout and source-safe counters to stderr on exit. It rejects:

- relative socket path;
- path outside `/private/tmp`, `/tmp`, or pytest temp roots in P0;
- existing non-socket path;
- TCP/HTTP URL;
- arbitrary sink/backend/module/config arguments;
- root execution;
- unknown arguments.

The CLI stops after `max-events` accepted events or SIGINT/SIGTERM.

- [ ] **Step 2: Write repository static fences**

Use `ast` and path-census assertions to prove:

- `common/runtime_diagnostics.py` imports standard library only;
- no P0 module imports `control_plane`, Agent OS, Slack, Linear, database, subprocess, requests/httpx, OTel, Grafana, Prometheus, Loki, or Jaeger clients;
- no P0 module calls `open()` except JSON-line stream supplied by caller;
- no P0 module contains lifecycle mutation names such as `create_job`, `claim_job`, `requeue`, `retry`, `cancel_worker`, `write_runtime_binding`;
- no `sqlite3`, `duckdb`, `psycopg`, or file-backed event store;
- no TCP socket family;
- no logging of raw packet;
- exact changed paths match the P0 allow-list.

- [ ] **Step 3: Run tests and verify RED**

```bash
python -m pytest tests/test_runtime_observability_static_fences.py -q
```

- [ ] **Step 4: Implement the narrow CLI**

Use `argparse`, `signal`, and one bound `AF_UNIX/SOCK_DGRAM` socket. Refuse root with `os.geteuid() == 0`. Apply `umask(0o077)`, create the parent only when it is already an owned disposable directory, bind with mode `0o600`, remove the socket in `finally` only after verifying it remains a socket owned by the current UID, and never recursively delete directories.

The CLI is P0 proof tooling. Production launchd/socket activation is a later wave and must not reuse permissive disposable path rules.

- [ ] **Step 5: Run all P0 tests and verify GREEN**

```bash
python -m pytest \
  tests/test_runtime_diagnostics_contract.py \
  tests/test_runtime_diagnostics_emitter.py \
  tests/test_runtime_observability_contract.py \
  tests/test_runtime_observability_sinks.py \
  tests/test_runtime_observability_sidecar.py \
  tests/test_runtime_observability_static_fences.py -q
```

- [ ] **Step 6: Commit Task 7**

```bash
git add \
  scripts/runtime_observability_sidecar.py \
  integrations/runtime_observability/__init__.py \
  tests/test_runtime_observability_static_fences.py
git commit -m "feat(observability): add disposable sidecar proof entrypoint"
```

---

### Task 8: Prove producer failure cannot alter a domain operation

**Files:**
- Modify: `tests/test_runtime_diagnostics_emitter.py`
- Create: `tests/fixtures/runtime_observability_domain_stub.py`

**Interfaces:**
- Consumes: producer emitter protocol.
- Produces: direct evidence of failure isolation without editing a real runtime owner.

- [ ] **Step 1: Add the deterministic domain stub**

```python
from __future__ import annotations

from dataclasses import dataclass

from common.runtime_diagnostics import RuntimeDiagnosticEmitter

@dataclass(frozen=True)
class DomainResult:
    value: str


def run_domain_operation(emitter: RuntimeDiagnosticEmitter) -> DomainResult:
    # The test injects an emitter whose emit() fails or raises internally.
    # The domain result is independent and returned exactly once.
    try:
        emitter.emit(TEST_EVENT)
    except Exception:
        # This guard models the future assembly rule; the concrete emitter
        # itself is also required not to raise ordinary errors.
        pass
    return DomainResult(value="canonical-domain-result")
```

Place a fully constructed fixed `TEST_EVENT` in the fixture.

- [ ] **Step 2: Add equivalence tests**

Run the domain stub with:

- null emitter;
- successful real socket emitter;
- missing socket;
- permission error;
- would-block emitter;
- fake emitter that raises `RuntimeError`.

Every returned `DomainResult` must be byte/equality-identical.

- [ ] **Step 3: Run equivalence tests and verify RED then GREEN**

Before the fixture/test exists, collection is RED. After implementation:

```bash
python -m pytest \
  tests/test_runtime_diagnostics_emitter.py -q
```

Expected: all pass.

- [ ] **Step 4: Commit Task 8**

```bash
git add tests/fixtures/runtime_observability_domain_stub.py tests/test_runtime_diagnostics_emitter.py
git commit -m "test(observability): prove domain outcome is telemetry-independent"
```

---

### Task 9: Run repository verification and write the continuation record

**Files:**
- Create: `research/MASTERMIND_RUNTIME_OBSERVABILITY_P0_EVIDENCE_2026-08-30.md`

**Interfaces:**
- Consumes: exact candidate head and test output.
- Produces: immutable evidence and exact OBS-H0/OBS-I1 continuation boundary.

- [ ] **Step 1: Run focused verification**

```bash
python -m pytest \
  tests/test_runtime_diagnostics_contract.py \
  tests/test_runtime_diagnostics_emitter.py \
  tests/test_runtime_observability_contract.py \
  tests/test_runtime_observability_sinks.py \
  tests/test_runtime_observability_sidecar.py \
  tests/test_runtime_observability_static_fences.py -q
```

Record exact counts and duration.

- [ ] **Step 2: Run adjacent shared-redaction tests**

```bash
python -m pytest tests/test_secret_redaction.py -q
```

- [ ] **Step 3: Run full repository test**

```bash
python -m pytest -q
```

Record exact pass/fail/skip counts. Do not call a partial suite full CI.

- [ ] **Step 4: Run syntax and diff checks**

```bash
python -m compileall -q \
  common/runtime_diagnostics.py \
  integrations/runtime_observability \
  scripts/runtime_observability_sidecar.py

git diff --check
git status --short
git diff --name-only "$(git merge-base origin/master HEAD)"...HEAD
```

The changed-path census must match the P0 allow-list plus this evidence file.

- [ ] **Step 5: Perform the manual disposable canary**

Start the CLI as a non-root user on a disposable socket, emit one canary using `UnixDatagramRuntimeDiagnosticEmitter`, and capture:

- producer return `True`;
- one accepted JSON line;
- exact event SHA-256;
- deterministic trace and span IDs;
- metrics labels with no correlation IDs;
- clean sidecar exit and socket removal.

Then stop the sidecar and emit the same event again. Capture producer return `False` and identical domain-operation result.

- [ ] **Step 6: Write the evidence record**

The evidence document must contain:

- exact protected basis;
- exact F0 head;
- exact P0 branch/head/tree;
- changed-path census;
- RED evidence from each task;
- GREEN focused/full tests;
- manual canary receipts;
- secret/cardinality/authority/failure-isolation findings;
- explicit `BUILT_NOT_PROVEN / PRODUCTION_INERT` state;
- exact non-goals;
- exact continuation missions:
  - OBS-H0 owns isolated Alloy collection and persistent telemetry queue;
  - OBS-I1 owns first real Worker Broker/Harness instrumentation only after collision re-check;
- stop statement forbidding install/arm/deploy from this carrier.

- [ ] **Step 7: Commit the evidence record**

```bash
git add research/MASTERMIND_RUNTIME_OBSERVABILITY_P0_EVIDENCE_2026-08-30.md
git commit -m "docs(observability): record P0 diagnostic sidecar evidence"
```

---

## Self-review checklist

Before opening the P0 PR:

1. Every spec requirement assigned to P0 has a task and test.
2. The plan contains no `TBD`, `TODO`, “similar to,” generic error-handling instruction, or unnamed test requirement.
3. Function/type names are consistent across tasks.
4. No task modifies an existing runtime owner.
5. No third-party dependency enters sealed or sidecar P0 code.
6. No high-cardinality correlation coordinate enters metrics.
7. No free-form text or secret-bearing field enters the envelope.
8. Emitter failure is proven nonblocking and outcome-independent.
9. Sidecar dedupe is bounded and explicitly non-durable/non-authoritative.
10. P0 remains production-inert and has an exact continuation handoff.
