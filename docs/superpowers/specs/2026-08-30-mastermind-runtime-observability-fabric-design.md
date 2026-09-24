# Mastermind Runtime Observability Fabric Design

**Status:** CEO architecture freeze  
**Date:** 2026-08-30  
**Parent operation:** `mastermind-runtime-observability-fabric-20260830-sol-pro-001`  
**F0 operation:** `mastermind-runtime-observability-fabric-f0-architecture-20260830-sol-001`  
**Protected source basis:** `mastermindx-market-intelligence/Mastermind@28d365cceaef6efb0a26e0ac9af51ead44695d60`  
**Skillpack:** `mastermind.sol_skillpack.v1` v1.0.1 / bootstrap-major 1  
**Architecture companion:** `research/MASTERMIND_RUNTIME_OBSERVABILITY_FABRIC_F0_ARCHITECTURE_2026-08-30.md`  
**Authority:** normative design for derived runtime diagnostic evidence. No runtime or organizational authority is granted by this document.

---

## 1. Design objective

Build a failure-isolated diagnostic substrate that can correlate physical execution evidence across Mastermind’s existing Executive, Worker, Operator Harness, Agent Dialogue, Agent Relay, Wake, Control Room, provider, and host boundaries.

The substrate must satisfy both statements simultaneously:

1. It is useful enough to localize a real stuck, slow, failed, disconnected, restarted, or resource-starved execution.
2. Removing or breaking the complete observability subsystem cannot change canonical work admission, authority, execution, retry, result, transport, or completion behavior.

---

## 2. Ownership and precedence

### 2.1 Canonical owners remain unchanged

| Truth | Owner |
|---|---|
| Job / Attempt / Worker / Event lifecycle | Executive OS |
| current Attempt, lease, fence, quota, retry/requeue | Executive OS |
| provider/session/process execution evidence | Worker / Operator Harness owner |
| durable organizational workstream, decision, discovery, handoff | Agent OS |
| dialogue parent/messages and Slack transport | Agent Dialogue / Agent Relay |
| attention obligation and delivery | Executive Wake Fabric |
| exact Sol action target | current SessionTarget / RuntimeBinding / exact-Sol authority owner |
| code, commits, PR, CI, release evidence | GitHub |
| selective portfolio projection | Linear |
| cross-owner operating cockpit | existing Steward / Control Room |
| runtime diagnostic evidence | Runtime Observability Fabric, derived and non-authoritative |

### 2.2 Precedence law

When telemetry conflicts with a canonical owner, telemetry is marked inconsistent or stale. It never rewrites the owner.

### 2.3 Effect law

No runtime diagnostic function may:

- create a Job, Attempt, Worker, dialogue, Wake, RuntimeBinding, or provider session;
- call a canonical write API;
- authorize or perform retry, requeue, cancellation, transfer, placement, merge, release, deployment, or acceptance;
- block waiting for a collector or backend;
- throw into the owning runtime because diagnostics are missing or broken;
- persist business lifecycle state;
- interpret missing telemetry as proof of non-execution.

---

## 3. Component model

### 3.1 `common.runtime_diagnostics`

A sealed-runtime-safe facade imported by existing first-party processes.

Responsibilities:

- expose immutable event types and closed policy;
- construct and validate an event before serialization;
- produce canonical JSON bytes;
- expose a no-op emitter and a nonblocking Unix datagram emitter;
- contain only Python standard-library imports plus existing stdlib-only `common` helpers;
- own no socket server, thread, queue, retry, exporter, backend client, or durable state.

### 3.2 `integrations.runtime_observability.contract`

The sidecar-side normative validator and projection helpers.

Responsibilities:

- parse untrusted datagram bytes;
- enforce exact schema, closed keys, types, values, bounds, and secret rules;
- derive deterministic trace and span IDs;
- derive a structured-log projection;
- derive a bounded-metrics projection;
- never infer lifecycle currentness, parentage, retry safety, or completion.

### 3.3 `integrations.runtime_observability.emitter`

Concrete nonblocking transport implementation if it is not kept wholly in `common.runtime_diagnostics`.

Responsibilities:

- `AF_UNIX`, `SOCK_DGRAM` only;
- `setblocking(False)` before send;
- one datagram per event;
- no connection handshake;
- no internal retry;
- no local queue;
- catch every transport `OSError` and return `False`;
- close the socket in every path;
- never log its own failure into the same diagnostic path.

### 3.4 `integrations.runtime_observability.sidecar`

An unprivileged receiver process.

Responsibilities:

- receive datagrams from launchd-activated service-specific sockets;
- enforce maximum read size before decode;
- validate and normalize events;
- suppress duplicate `event_id` in bounded process memory;
- project accepted events to injected sinks;
- maintain only bounded process-local counters and dedupe state;
- expose typed self-health through sinks/stdout;
- continue serving after malformed input;
- never write Executive or Agent OS stores.

### 3.5 Sinks

P0 sink protocol:

```python
class DiagnosticSink(Protocol):
    def emit(self, event: NormalizedDiagnosticEvent) -> None: ...
    def close(self) -> None: ...
```

Required P0 sinks:

- `JsonLineSink`: emits one canonical source-safe JSON line to an injected text stream;
- `InMemorySink`: tests only;
- `CompositeSink`: invokes fixed sinks independently and reports bounded sink failure counters without retrying business work.

Later sinks:

- OTel SDK/OTLP sink in the **sidecar-only optional runtime**;
- no OTel dependency in sealed producers.

---

## 4. Runtime diagnostic envelope v1

### 4.1 Schema identity

```text
mastermind.runtime_diagnostic/v1
```

### 4.2 Exact top-level keys

Required:

- `schema_version`;
- `event_id`;
- `observed_at`;
- `service`;
- `event_name`;
- `signal`;
- `outcome`;
- `correlation`;
- `dimensions`.

Optional:

- `duration_ms`.

No other top-level key is accepted.

### 4.3 Types and limits

| Field | Type | Bound |
|---|---|---|
| encoded datagram | UTF-8 JSON object | `<= 8192` bytes including newline if one is used |
| `event_id` | canonical lowercase UUID string | exactly UUID v4 for producer-created events |
| `observed_at` | aware UTC timestamp | ISO-8601, microseconds allowed, offset must be `+00:00` or `Z` |
| `service` | closed enum | see 4.4 |
| `event_name` | closed enum | see 4.5 |
| `signal` | closed enum | `POINT`, `DURATION` |
| `outcome` | closed enum | `STARTED`, `SUCCEEDED`, `FAILED`, `CANCELLED`, `REFUSED`, `UNAVAILABLE`, `UNKNOWN` |
| `duration_ms` | finite number | `0 <= value <= 90000000`; required only for `DURATION` |
| `correlation` | object | at most 12 exact keys |
| `dimensions` | object | at most 12 exact keys |
| every string | UTF-8 string | nonempty after trim; per-field ceiling `<= 128` unless lower below |

Boolean values are not accepted where an integer or float is required.

### 4.4 Service vocabulary

V1 services:

- `executive-control`;
- `worker-broker`;
- `operator-harness`;
- `provider-adapter`;
- `agent-dialogue`;
- `agent-relay`;
- `wake`;
- `control-room`;
- `runtime-observability-sidecar`;
- `runtime-observability-collector`.

Adding a service requires a schema-version-compatible policy change and tests. Callers cannot create service names dynamically.

### 4.5 Event-name vocabulary

Initial V1 events:

- `diagnostics.canary`;
- `service.started`;
- `service.stopped`;
- `service.restarted`;
- `broker.request.started`;
- `broker.request.completed`;
- `broker.request.refused`;
- `broker.request.interrupted`;
- `harness.session.started`;
- `harness.session.resumed`;
- `harness.session.stopped`;
- `harness.session.cancelled`;
- `harness.turn.started`;
- `harness.turn.completed`;
- `harness.turn.interrupted`;
- `provider.turn.started`;
- `provider.turn.completed`;
- `provider.turn.failed`;
- `result.collection.started`;
- `result.collection.completed`;
- `result.collection.refused`;
- `dialogue.projection.started`;
- `dialogue.projection.completed`;
- `dialogue.projection.failed`;
- `relay.delivery.started`;
- `relay.delivery.completed`;
- `relay.delivery.failed`;
- `wake.delivery.started`;
- `wake.delivery.completed`;
- `wake.delivery.failed`;
- `collector.export.failed`;
- `collector.export.recovered`.

The vocabulary describes evidence boundaries. It does not mirror or replace domain lifecycle states.

### 4.6 Correlation keys

Allowed keys:

- `root_job_id`;
- `job_id`;
- `attempt_id`;
- `worker_id`;
- `run_id`;
- `logical_operation_id`;
- `operation_id`;
- `turn_id`;
- `process_generation_id`;
- `dialogue_parent_id`;
- `wake_id`;
- `request_id`.

Each value must be a bounded canonical identifier with an allowed semantic prefix. P0 policy accepts only:

```text
root-job:
job:
attempt:
worker:
run:
logical-operation:
operation:
ohfw-op:
ohfw-turn:
process-generation:
dialogue-parent:
wake:
request:
```

Existing domain identifiers with a different current prefix must be projected by a reviewed adapter into one of these diagnostic prefixes without changing the underlying canonical value. For example, a canonical `ohf-op:` identifier may be carried as `operation:ohf-op:...`.

Unprefixed token-like strings are rejected. The sidecar does not accept an email, account name, path, URL, arbitrary UUID, provider cookie, or model-authored label as a correlation ID.

### 4.7 Dimension keys and values

Allowed keys:

- `phase`;
- `operation_class`;
- `harness`;
- `provider_class`;
- `transport`;
- `error_class`;
- `host_role`;
- `environment`;
- `deployment_channel`;
- `evidence_source`;
- `result_class`;
- `availability`.

Each key has a closed value set in policy. Initial values:

**phase**

- `admission`, `claim`, `broker`, `harness`, `provider`, `collection`, `projection`, `dialogue`, `relay`, `wake`, `control-room`, `collector`.

**operation_class**

- `start`, `status`, `collect`, `cancel`, `validate`, `autonomy-canary`, `ohf-validate`, `ohf-identity`, `ohf-start`, `ohf-resume`, `ohf-begin-turn`, `ohf-collect-turn`, `ohf-interrupt`, `ohf-stop`, `ohf-cancel`, `ohf-reconcile`, `ohf-reconcile-absence`, `none`.

**harness**

- `sealed-worker`, `operator-harness`, `none`.

**provider_class**

- `codex`, `claude`, `cursor`, `grok`, `glm`, `qwen`, `other-reviewed`, `none`.

**transport**

- `unix-datagram`, `unix-stream`, `otlp-http`, `otlp-grpc`, `https`, `slack`, `none`.

**error_class**

- `none`, `validation`, `authorization`, `capacity`, `timeout`, `rate-limit`, `authentication`, `transport`, `provider`, `process`, `protocol`, `result`, `projection`, `storage`, `resource`, `unknown`.

**host_role**

- `control`, `worker`, `relay`, `diagnostics`, `mixed-reviewed`, `unknown`.

**environment**

- `test`, `canary`, `production`, `development`.

**deployment_channel**

- `protected`, `candidate`, `disposable`, `unknown`.

**evidence_source**

- `runtime-emitter`, `sidecar`, `alloy`, `launchd-log`, `host-metric`, `backend-query`.

**result_class**

- `none`, `completed`, `failed`, `cancelled`, `refused`, `effect-unknown`, `unavailable`, `unknown`.

**availability**

- `observed`, `rejected`, `dropped`, `unavailable`, `stale`, `absent`, `unknown`.

Dimensions must never contain canonical IDs, paths, URLs, account names, repository names, PR numbers, hashes, timestamps, or free-form error messages.

---

## 5. Secret and content exclusion

### 5.1 Structural exclusion

The schema contains no field for:

- prompt;
- output;
- message body;
- exception text;
- stack trace;
- tool arguments or output;
- environment;
- URL;
- path;
- command line;
- HTTP body or headers;
- Slack text;
- account identity;
- source contents.

Unknown keys fail before transport or sink projection.

### 5.2 Shape exclusion

Except for exact prefixed canonical identifiers, string values that match known credential prefixes, JWT shapes, unprefixed long hex, or unprefixed long base64url/token shapes are rejected rather than silently redacted into an event.

Rationale: a diagnostic producer must not turn accidental secret submission into a successful but lossy event. Redaction is a final protection for sidecar/collector self-errors, not permission to admit secret-bearing business data.

### 5.3 External errors

When sidecar/collector code must surface text from an external library or backend, it passes through `common.redaction.sanitize_external_text` before any log or API projection. The runtime envelope itself never accepts external error text.

---

## 6. Canonical serialization

Events serialize as UTF-8 JSON using:

```python
json.dumps(
    document,
    sort_keys=True,
    separators=(",", ":"),
    ensure_ascii=True,
    allow_nan=False,
).encode("utf-8")
```

The sender emits exactly one datagram containing the canonical bytes. A trailing newline is optional for datagram transport and must not be required by the receiver. JSON line sinks add exactly one newline after canonical serialization.

The event digest is:

```text
sha256(canonical_event_bytes)
```

It may be emitted in the structured-log projection. It is diagnostic dedupe/evidence only, not operation identity.

---

## 7. Producer API

Normative interface:

```python
@dataclass(frozen=True)
class RuntimeDiagnosticEvent:
    event_id: str
    observed_at: str
    service: str
    event_name: str
    signal: str
    outcome: str
    correlation: Mapping[str, str]
    dimensions: Mapping[str, str]
    duration_ms: float | None = None

class RuntimeDiagnosticEmitter(Protocol):
    def emit(self, event: RuntimeDiagnosticEvent) -> bool: ...

class NullRuntimeDiagnosticEmitter:
    def emit(self, event: RuntimeDiagnosticEvent) -> bool:
        return False

class UnixDatagramRuntimeDiagnosticEmitter:
    def __init__(self, socket_path: Path, *, max_packet_bytes: int = 8192): ...
    def emit(self, event: RuntimeDiagnosticEvent) -> bool: ...
```

Construction helper:

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
    now: Callable[[], datetime] = utc_now,
    uuid_factory: Callable[[], UUID] = uuid4,
) -> RuntimeDiagnosticEvent: ...
```

The builder validates before returning. `emit()` validates again before serialization because callers may construct a dataclass directly.

### 7.1 Nonblocking law

`UnixDatagramRuntimeDiagnosticEmitter.emit()`:

1. validates and serializes before opening the socket;
2. returns `False` for invalid events rather than sending;
3. creates a fresh `AF_UNIX/SOCK_DGRAM` socket;
4. calls `setblocking(False)`;
5. sends one datagram with `sendto()`;
6. returns `True` only when the full packet is accepted by the kernel;
7. catches `BlockingIOError`, `FileNotFoundError`, `PermissionError`, and all other `OSError` and returns `False`;
8. catches no domain exception from the owning service because all diagnostic exceptions are contained;
9. closes the socket in `finally`;
10. performs no retry, sleep, backoff, DNS, network, file write, log write, thread, queue, or callback.

A programming error in a caller’s diagnostic payload must not fail business work. The emitter therefore returns `False`; tests and sidecar counters make the defect visible.

---

## 8. Sidecar API and behavior

Normative types:

```python
@dataclass(frozen=True)
class DiagnosticTraceCoordinates:
    trace_id: str  # 32 lowercase hex
    span_id: str   # 16 lowercase hex
    trace_basis: str

@dataclass(frozen=True)
class DiagnosticMetricPoint:
    name: str
    value: float
    labels: Mapping[str, str]

@dataclass(frozen=True)
class NormalizedDiagnosticEvent:
    event: RuntimeDiagnosticEvent
    event_sha256: str
    trace: DiagnosticTraceCoordinates
    metrics: tuple[DiagnosticMetricPoint, ...]
    log_document: Mapping[str, object]

class RuntimeDiagnosticContractError(ValueError): ...

def parse_runtime_diagnostic_packet(raw: bytes) -> NormalizedDiagnosticEvent: ...
```

### 8.1 Trace derivation

```text
trace_basis = first present of attempt_id, run_id, logical_operation_id,
              operation_id, event_id
trace_id = first 16 bytes of SHA-256(
    b"mastermind.runtime.trace/v1\x00" + trace_basis.encode("utf-8")
)
span_id = first 8 bytes of SHA-256(
    b"mastermind.runtime.span/v1\x00" +
    trace_id_bytes + b"\x00" + service + b"\x00" + event_name + b"\x00" + event_id
)
```

All-zero derived IDs are replaced by hashing with a fixed second namespace. The sidecar never accepts caller-provided trace or span IDs in V1.

### 8.2 Metrics projection

Each accepted event produces:

- `mastermind_runtime_diagnostic_events_total` counter with bounded dimension labels plus `service`, `event_name`, and `outcome`;
- for `DURATION`, `mastermind_runtime_diagnostic_duration_ms` observation with the same bounded labels;
- sidecar internal counters for accepted, rejected, duplicate, and sink-failed events with only reason-class labels.

The projection function is mechanically prohibited from reading `correlation` when building labels.

### 8.3 Structured-log projection

The log document contains:

- schema version;
- event ID and digest;
- observed time;
- service/event/signal/outcome/duration;
- exact correlation object;
- exact dimensions object;
- trace ID and span ID;
- source `runtime-diagnostic-sidecar`;
- acceptance state `OBSERVED`.

It contains no raw packet, exception, environment, peer credential, or socket path.

### 8.4 Dedupe

The sidecar retains an `OrderedDict[event_id, observed_monotonic]` with:

- configurable maximum entries, default 4096;
- configurable maximum age, default 15 minutes;
- deterministic oldest-first eviction;
- no durable persistence;
- no effect on canonical execution;
- duplicate events counted and not re-emitted within the window.

Dedupe exists only to avoid accidental duplicate backend evidence; it is not operation idempotency.

### 8.5 Sink isolation

One failing sink cannot prevent another fixed sink from receiving the event. `CompositeSink` catches sink exceptions, reports a bounded failure class, and continues. It does not retry within the sidecar event path.

OTLP exporter retry/queue behavior, when introduced, belongs to Alloy or the sidecar OTel exporter’s bounded telemetry policy and remains independent of business operations.

---

## 9. Process and socket topology

### 9.1 Production socket pattern

Production sidecar is launchd socket-activated with separately permissioned Unix datagram sockets, conceptually:

```text
.../observability/control.dgram
.../observability/worker.dgram
.../observability/relay.dgram
```

Each socket is owned/mode-bound for the exact producer principal. The dedicated Worker Broker keeps `InitGroups=false`; no broad supplemental group is added.

P0 uses disposable temporary sockets under a test-owned directory. It does not author or install launchd files.

### 9.2 Process privilege

The sidecar runs as a dedicated unprivileged principal. It does not run as root, control user, worker user, relay user, or Chairman user. Host preparation may use launchd/root only to create exact accounts, directories, sockets, and service definitions after merged exact-commit review.

### 9.3 Sidecar command

Future production entrypoint:

```text
python -I -B scripts/runtime_observability_sidecar.py \
  --config /exact/root-owned/config.json
```

P0 entrypoint accepts only test/disposable fixed configuration. No generic command execution, dynamic module loading, arbitrary sink class, URL from a model, or environment-dump mode exists.

---

## 10. Alloy and backend contract

### 10.1 Host Alloy

- receives sidecar OTLP on loopback or Unix socket;
- tails exact allowlisted launchd stdout/stderr paths;
- gathers bounded host metrics;
- applies redaction/drop filters before remote export;
- removes prohibited attributes;
- uses bounded batches;
- uses a bounded persistent file queue for telemetry export only;
- emits self-health;
- never calls Executive or Agent OS APIs.

### 10.2 Prometheus

- bounded local TSDB retention by time and size;
- no high-cardinality IDs as labels;
- no remote write in initial deployment unless separately justified;
- dead-man/self-health alerts are diagnostic only.

### 10.3 Loki

- single-binary initial topology;
- local filesystem/object-store choice proven against retention and DR needs;
- no direct public exposure;
- no built-in-auth assumption—authentication lives at proxy/private boundary;
- log streams label only bounded service/host-role/environment/source fields;
- exact runtime IDs stay in log body fields.

### 10.4 Jaeger

- Jaeger 2 all-in-one + Badger for modest initial trace volume;
- OTLP ingest;
- one instance, explicit non-HA state;
- bounded retention/storage;
- Grafana’s built-in Jaeger datasource for exploration and trace-to-log linkage;
- future Tempo migration only after an evidence-based scale/availability gate.

### 10.5 Grafana

- human diagnostic/exploration interface, not canonical cockpit;
- provisioned data sources and dashboards from version-controlled files;
- production metadata in PostgreSQL;
- least-privilege service accounts;
- authenticated private access;
- dashboard state does not become company truth.

---

## 11. Control Room and MCP integration

### 11.1 Control Room

A later wave adds a small attributed projection:

- diagnostic availability and freshness;
- last observed diagnostic boundary;
- bounded latency/failure summary;
- deep links to exact Grafana/Jaeger/Loki queries;
- source identity and observed timestamp;
- explicit `UNAVAILABLE`, `STALE`, `ABSENT`, and `UNKNOWN` states.

It does not add a second cockpit, incident lifecycle, or state editor.

### 11.2 MCP

A later wave extends the existing capability registry. Required properties:

- exact `mcp-grafana` version and checksum;
- `--disable-write` or equivalent write-tool removal;
- exact read-only enabled tools;
- least-privilege Grafana token stored outside source;
- HTTPS endpoint without credentials/query/fragment;
- exact server identity/version observation;
- exact effective tool schema + security annotation digest;
- schema drift refusal;
- production profile remains read-only, approval never, write-capable false;
- raw SQL and administrative tools excluded;
- direct backend credentials never given to model workers.

---

## 12. Testing matrix

### 12.1 Contract tests

- exact valid point event;
- exact valid duration event;
- unknown top-level key;
- unknown correlation key;
- unknown dimension key;
- unknown service/event/signal/outcome/value;
- missing required field;
- boolean-as-number rejection;
- NaN/Infinity rejection;
- naive/non-UTC timestamp rejection;
- wrong UUID version/case;
- packet at and above 8 KiB boundary;
- excessive object fields;
- control character;
- email/path/URL in prohibited field;
- JWT, known credential prefix, unprefixed long hex, unprefixed long token;
- valid prefixed canonical ID containing a long digest;
- deterministic canonical bytes/digest;
- deterministic trace/span IDs;
- P1/P2 distinct trace IDs and shared logical-operation attribute;
- metric projection contains no correlation values.

### 12.2 Emitter tests

- socket receives exact packet;
- socket missing;
- permission denied;
- would-block/full buffer;
- invalid event;
- oversized event;
- socket closes every path;
- `setblocking(False)` occurs before send;
- no retry/sleep/file/log/thread/network calls;
- null emitter returns `False`;
- producer-domain outcome unchanged when emitter fails.

### 12.3 Sidecar tests

- accepts and emits one event;
- malformed UTF-8/JSON/object;
- truncated/oversized datagram;
- duplicate suppression;
- bounded dedupe eviction and age expiry;
- one sink fails while another receives;
- sink errors are redacted and bounded;
- malformed packet does not terminate serve loop;
- shutdown closes sinks and socket cleanly;
- no lifecycle or external write imports;
- stdout JSON contains only the allowed projection.

### 12.4 Later integration tests

- Alloy restart with persistent queue;
- remote diagnostics-node outage and recovery;
- backend storage ceiling;
- collector redaction canaries;
- real broker/harness Attempt with telemetry on/off comparison;
- relay outage;
- safe P1/P2 rollover;
- Mac crash/reboot evidence;
- MCP read allow-list and write/schema drift refusal;
- Control Room source attribution and stale/unavailable states.

---

## 13. Release and production gates

A code merge is not a deployment. A deployment is not production proof.

Required progression:

```text
SPEC_ONLY
  -> P0 BUILT_NOT_PROVEN / PRODUCTION_INERT
  -> isolated host canary
  -> disposable diagnostics-node canary
  -> one instrumented real service behind default-off injection
  -> real Attempt canary with telemetry on/off equivalence
  -> small host fleet
  -> Control Room/MCP read integration
  -> retention/DR proof
  -> production acceptance
```

Every stage has exact artifacts, revision, configuration digest, tests, observed outputs, rollback, and stop condition. No stage inherits authority from a green dashboard.

---

## 14. Rejected widening in OBS-P0

OBS-P0 must not:

- edit `control_plane/executive_service.py`;
- edit `control_plane/executive_runtime.py`;
- edit `control_plane/executive_worker_broker.py`;
- edit Operator Harness contracts/wire/adapters;
- edit Agent Dialogue, Relay, Wake, or Control Room;
- edit launchd/systemd/installers;
- add Grafana/Alloy/Prometheus/Loki/Jaeger configuration;
- add OTel third-party dependencies;
- open a TCP/HTTP port;
- create a durable database or file-backed event store;
- add alert-driven actions;
- add MCP capability grants;
- install or arm anything on a production host.

The wave ends after the producer/sidecar contract is real and independently proven.
