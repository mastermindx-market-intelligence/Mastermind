# Mastermind Runtime Observability Fabric — F0 Architecture Freeze

**Date:** 2026-08-30  
**Program CEO:** Sol, AI CEO  
**Chairman:** Chris  
**Parent operation:** `mastermind-runtime-observability-fabric-20260830-sol-pro-001`  
**F0 child operation:** `mastermind-runtime-observability-fabric-f0-architecture-20260830-sol-001`  
**Protected procedure pin:** `mastermindx-market-intelligence/Mastermind@28d365cceaef6efb0a26e0ac9af51ead44695d60`  
**Skillpack:** `mastermind.sol_skillpack.v1` v1.0.1 / bootstrap-major 1  
**Macro archaeology pin:** `mastermindx-market-intelligence/macro@ede7e065a90b294e9835e98e5326a84e1c14d038`  
**Capability state:** `SPEC_ONLY / RECORDS_ONLY` until a separately reviewed implementation carrier proves otherwise  
**Authority:** architecture, semantic, privacy, topology, sequencing, and acceptance law only. This document creates no Job, Attempt, Worker, retry, provider session, RuntimeBinding, lifecycle event, service, socket, credential, host mutation, deployment, alert, Slack post, Linear update, or production capability.

---

## 1. Executive ruling

Mastermind needs one coherent **derived diagnostic evidence plane** for its physical and runtime behavior.

The user job is not “operate Grafana.” The user job is:

> Start from a company/runtime object such as a Job, Attempt, Worker, dialogue, service, host, or deployment and determine where progress stopped, what evidence supports that diagnosis, what component failed, what code or release was involved, and what repair decision is lawful.

The machine job is:

> Preserve enough bounded, source-attributed, failure-independent evidence to reconstruct cross-service execution without granting telemetry any lifecycle, retry, placement, authority, or organizational-completion power.

The selected initial architecture is:

```text
SEALED EXECUTIVE / WORKER / RELAY PROCESSES
  - existing canonical lifecycle and transport owners
  - no OpenTelemetry SDK import
  - tiny closed stdlib diagnostic envelope
  - nonblocking Unix datagram emission
                    │
                    ▼
UNPRIVILEGED HOST DIAGNOSTIC SIDECAR
  - validates the closed envelope
  - derives trace/log/metric coordinates
  - emits source-safe structured logs
  - exports OTLP to local Alloy
  - owns no lifecycle or retry state
                    │
                    ▼
GRAFANA ALLOY ON EACH RUNTIME HOST
  - receives OTLP from the sidecar
  - tails existing bounded launchd logs
  - gathers bounded host/process metrics
  - redacts, filters, batches, and queues
  - exports over authenticated private transport
                    │
                    ▼
FAILURE-INDEPENDENT LINUX DIAGNOSTICS NODE
  - Prometheus 3.x local TSDB for metrics
  - Loki 3.x single-binary for logs
  - Jaeger 2.x all-in-one + Badger for modest trace volume
  - Grafana OSS for human exploration
  - PostgreSQL for production Grafana metadata
  - authenticating reverse proxy / private network boundary
                    │
          ┌─────────┴─────────┐
          ▼                   ▼
CONTROL ROOM POINTERS     READ-ONLY MCP
  - bounded status        - existing capability registry
  - evidence links        - exact tool allow-list
  - no state rewrite      - schema/security digest
```

The first production trace backend is **Jaeger 2**, not Tempo 3. Tempo 3.0 introduced a Kafka-compatible queue requirement and recommends distributed/object-storage deployment for production. Introducing a new durable queue and distributed trace topology solely to satisfy initial observability would violate the company’s no-duplicate-control-plane and proportionality laws. Tempo remains a future scale option behind an explicit evidence gate.

---

## 2. Outcome model

### 2.1 Primary persona

The primary persona is an action-authoritative Sol investigating a real runtime problem. Secondary personas are the Chairman, CTO Sol, operators, security reviewers, and infrastructure maintainers.

### 2.2 Primary task

Given one exact runtime object, answer:

1. What is its canonical identity and current lifecycle truth?
2. Which diagnostic segments were actually observed?
3. At what boundary did progress stop or degrade?
4. Which evidence is missing, stale, rejected, or unavailable?
5. Which host, process, provider class, transport, or release was involved?
6. What code or configuration should be inspected?
7. What actions are lawful, and which require Executive OS or an existing owner?

### 2.3 Ten-out-of-ten experience

```text
Job / Attempt / Worker / operation / service / host / deployment
  -> exact canonical read from the owning system
  -> bounded diagnostics lookup by the same identity
  -> chronological cross-service evidence path
  -> first missing or failed boundary
  -> exact release / host / component attribution
  -> linked logs, metrics, and traces
  -> explicit uncertainty and evidence gaps
  -> repair recommendation that does not impersonate authority
```

The system must be useful when healthy, degraded, partially instrumented, disconnected, or recovering from a host crash.

### 2.4 Value model

**User value:** eliminates manual process hunting and multi-log archaeology.  
**Machine value:** gives Sol and operators a bounded diagnostic substrate for investigation and review.  
**Research value:** creates measured latency, failure, restart, and transport evidence for improving runtime architecture.  
**Commercial value:** improves reliability and operational confidence without exposing internal prompts or credentials.  
**Data-moat value:** creates a longitudinal corpus of typed runtime behavior tied to exact releases and canonical execution identities, while keeping it explicitly non-authoritative.

---

## 3. Non-negotiable authority boundaries

Observability is derived evidence. It never owns or changes:

- Job lifecycle;
- Attempt lifecycle;
- Worker lifecycle;
- Executive Event truth;
- CEO-intent admission;
- child responsibility identity;
- current Attempt or current Worker authority;
- leases, fences, quotas, or retry eligibility;
- RuntimeBinding;
- provider/account/host eligibility or placement;
- Agent OS workstream state;
- Slack dialogue identity or transport state;
- Wake obligations, delivery, or acknowledgement;
- merge, release, deployment, or production acceptance state;
- Linear project state;
- organizational completion.

Mechanical laws:

1. A successful trace does not complete a Job.
2. A missing trace does not prove an Attempt never executed.
3. A process exit does not authorize retry.
4. A Grafana alert cannot create, cancel, requeue, transfer, or accept work.
5. A Loki log line cannot make Slack or Linear canonical.
6. A telemetry outage is reported as `UNAVAILABLE`; it is never rendered as healthy.
7. Turning telemetry fully off must not change the outcome of any Executive, Worker, Operator Harness, Agent Dialogue, Agent Relay, Wake, or Control Room operation.
8. No telemetry callback may sit on a commit-before-effect, authorization, lease, fence, cleanup, cancellation, or result-validation critical path.
9. No generic retry, delivery queue, worker registry, session registry, or lifecycle table may be created inside this program.
10. Control Room may display attributed diagnostic pointers and degradation, but may not rewrite canonical state based on telemetry.

---

## 4. Current estate and capability ledger

The ledger below distinguishes source presence from production proof.

| Capability | State | Ruling |
|---|---|---|
| Executive Job/Attempt/Worker/Event lifecycle | `BUILT_NOT_PROVEN` for this program | Existing canonical owner; consume read-only |
| RuntimeBinding / exact current executor fences | `BUILT_NOT_PROVEN` for this program | Existing canonical owner; never infer from telemetry |
| Worker Broker typed AF_UNIX protocol | `BUILT_NOT_PROVEN` | Carries `run_id`, `job_id`, `worker_id`; closed wire stays unchanged in V1 |
| Operator Harness typed operation/session/turn generations | `BUILT_NOT_PROVEN` | Existing execution evidence; instrument around it without replacing it |
| Agent Dialogue / Agent Relay / Wake | `PARTIAL / active owners` | Active continuity work; observability is evidence-only and path-disjoint |
| Separate bounded launchd stdout/stderr files | `BUILT_NOT_PROVEN` | Real collection seam; not sufficient alone for causal diagnosis |
| Failure-independent Linux/systemd host pattern | `BUILT_NOT_PROVEN` | Existing remote Control Room pattern proves topology is viable, not capacity |
| Shared secret-shape redaction | `BUILT_NOT_PROVEN` | Reuse `common.redaction`; no new redaction owner |
| MCP capability allow-list and schema digest | `BUILT_NOT_PROVEN / PRODUCTION_INERT` | Extend later through existing owner only |
| Runtime diagnostic envelope contract | `NOT_BUILT` | First implementation wave |
| Nonblocking stdlib emitter | `NOT_BUILT` | First implementation wave |
| Diagnostic sidecar | `NOT_BUILT` | First implementation wave |
| Alloy host collector | `NOT_BUILT` | Host collection wave |
| Prometheus metrics backend | `NOT_BUILT` | Diagnostics-node wave |
| Loki log backend | `NOT_BUILT` | Diagnostics-node wave |
| Jaeger trace backend | `NOT_BUILT` | Diagnostics-node wave |
| Grafana human exploration | `NOT_BUILT` | Diagnostics-node/dashboard wave |
| Observability MCP grant | `NOT_BUILT` | Later read-only wave |
| Control Room diagnostic pointer projection | `NOT_BUILT` | Later integration wave; do not collide with current Steward/UI owners |
| Retention, backup, upgrade, rollback, and DR proof | `NOT_BUILT` | Reliability wave |
| Real incident / MTTD acceptance | `NOT_BUILT` | Final canary and production proof |

No dedicated Runtime Observability Agent OS workstream was found at the Macro archaeology pin. Two generic uses of “observability” in unrelated decision records do not constitute this program.

---

## 5. Current source and collision map

### 5.1 Protected source

- protected Mastermind master: `28d365cceaef6efb0a26e0ac9af51ead44695d60`;
- protected tree: `f55ab9d79b3ba5fa25bc090d3d7fa8a4ea4b0bf2`;
- required protected status: `test`;
- Skillpack v1.0.1 / bootstrap-major 1 loaded from the same commit;
- Macro main observed: `ede7e065a90b294e9835e98e5326a84e1c14d038`.

### 5.2 Active collision owners

**PR #265 — bounded Executive terminal return projection**

- owns `control_plane/executive_service.py` and its terminal-return seam;
- remains draft/hold and production-disarmed;
- F0 and the first observability implementation wave must not edit `executive_service.py`.

**PR #153 — Worker Browser B1 / Control Room review**

- owns current Control Room UI/server/runtime paths;
- the first observability implementation wave must not edit Control Room UI or server paths.

**Current Operator Continuity, Agent Dialogue, Agent Relay, Wake, exact-Sol authority, Steward, Capacity, and Worker Browser lanes**

- remain exclusive owners of their mutation surfaces;
- this program may consume their canonical identities and outputs as evidence;
- it may not widen their wire schemas, retries, placement, authority, or lifecycle during the first wave.

### 5.3 Disjoint first implementation surface

The first code carrier is limited to new paths plus one test-only package inclusion if required:

- `common/runtime_diagnostics.py`;
- `integrations/runtime_observability/__init__.py`;
- `integrations/runtime_observability/contract.py`;
- `integrations/runtime_observability/emitter.py`;
- `integrations/runtime_observability/sidecar.py`;
- `integrations/runtime_observability/sinks.py`;
- `scripts/runtime_observability_sidecar.py`;
- `tests/test_runtime_diagnostics_contract.py`;
- `tests/test_runtime_diagnostics_emitter.py`;
- `tests/test_runtime_observability_sidecar.py`.

No existing lifecycle, broker, harness, dialogue, relay, wake, Control Room, launchd, installer, capability-registry, or host path is modified in P0.

---

## 6. Alternatives considered

### 6.1 Direct OpenTelemetry SDK inside sealed processes — rejected

The Executive control and Worker Broker services deliberately run Python with `-I -S -B`. Their sealed dependency boundary is part of the security and reproducibility design. Adding the OTel SDK to those processes would:

- widen the trusted dependency closure;
- create exporter/backpressure behavior inside critical services;
- make telemetry configuration capable of affecting startup or shutdown;
- complicate sealed-runtime provisioning and attestation;
- make an observability outage more capable of harming execution.

The selected stdlib emitter keeps instrumentation dependency-free and nonblocking.

### 6.2 Reconstruct everything from stdout/stderr — rejected as final architecture

Existing bounded logs are valuable fallback evidence and the fastest initial collection seam. They are not enough to guarantee:

- exact cross-service Attempt correlation;
- bounded semantic fields;
- deterministic latency measurement;
- precise phase boundaries;
- reliable trace links;
- cardinality control;
- negative proof that prompts or secrets are absent.

Logs remain one signal, not the semantic contract.

### 6.3 Tempo 3 + Kafka-compatible queue + object storage — deferred

Tempo 3 is a viable future trace backend. It is not the proportional first deployment because current Tempo production architecture adds a queue and distributed/object-storage concerns that Mastermind does not otherwise need for modest runtime trace volume.

Promotion to Tempo requires observed evidence that at least one of the following cannot be met by Jaeger 2 + Badger:

- trace ingestion throughput;
- retention volume;
- query latency;
- failure recovery;
- horizontal scale;
- multi-instance availability;
- tenancy requirements.

The migration must preserve OTLP producers and dashboards so the backend can change without runtime instrumentation rebuild.

### 6.4 Grafana Alloy versus upstream Collector

Alloy is selected for V1 because one agent can receive OTLP, tail files, gather host metrics, apply OTel processing, and export Loki/Prometheus/OTLP signals. Upstream Collector remains an acceptable replacement if Alloy-specific behavior becomes a blocker. The runtime envelope and sidecar contract stay vendor-neutral.

### 6.5 A new observability database or incident lifecycle — rejected

Prometheus, Loki, and Jaeger are diagnostic backends, not a company lifecycle. The program does not create an incident database, diagnostic task queue, retry table, or canonical health state. Durable organizational findings and handoffs remain in Agent OS; code and proof remain in GitHub.

---

## 7. Semantic architecture

### 7.1 One closed envelope

The runtime-facing schema is `mastermind.runtime_diagnostic/v1`.

It is a bounded event envelope, not arbitrary structured logging. Producers cannot attach free-form dictionaries, prompts, outputs, exceptions, environment variables, file bodies, URLs with credentials, or model-authored labels.

Normative shape:

```json
{
  "schema_version": "mastermind.runtime_diagnostic/v1",
  "event_id": "4d6b31d2-5810-4f61-9610-416024c0bc19",
  "observed_at": "2026-08-30T12:34:56.123456+00:00",
  "service": "worker-broker",
  "event_name": "broker.request.completed",
  "signal": "duration",
  "outcome": "SUCCEEDED",
  "duration_ms": 182.4,
  "correlation": {
    "job_id": "job:...",
    "attempt_id": "attempt:...",
    "worker_id": "worker:...",
    "run_id": "run:...",
    "operation_id": "ohf-op:..."
  },
  "dimensions": {
    "phase": "broker",
    "operation_class": "ohf-collect-turn",
    "harness": "operator-harness",
    "provider_class": "codex",
    "transport": "unix",
    "error_class": "none",
    "host_role": "worker",
    "deployment_generation": "release:..."
  }
}
```

### 7.2 Closed fields and bounds

- maximum encoded envelope: 8 KiB;
- maximum correlation fields: 12;
- maximum dimension fields: 12;
- maximum identifier length: 128 bytes unless an existing canonical contract requires a lower limit;
- maximum event name length: 96 bytes;
- event names match a reviewed lowercase dotted vocabulary;
- timestamps are aware UTC RFC3339/ISO-8601;
- durations are finite, nonnegative, and at most 25 hours;
- unknown top-level, correlation, dimension, service, signal, outcome, or event-name values fail closed at the sidecar;
- producer helpers reject unknown fields before serialization;
- the socket sender catches transport errors and returns `False`; it never raises into the owning service.

### 7.3 Correlation coordinates

Allowed high-cardinality correlation coordinates include, where already known to the producer:

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

These coordinates may appear in traces and structured logs. They are forbidden as Prometheus metric labels.

### 7.4 Bounded metric dimensions

Only bounded enums are metric labels:

- service;
- event name from the closed vocabulary;
- outcome;
- phase;
- operation class from a closed set;
- harness class;
- provider class;
- transport class;
- error class;
- host role;
- environment;
- deployment channel.

Forbidden metric labels include every Job, Attempt, Worker, run, operation, request, trace, session, dialogue, Wake, PR, repository path, filesystem path, URL, account, or personal identity.

### 7.5 Trace identity

V1 does not add `traceparent` to the closed Worker Broker or Operator Harness wire.

The sidecar derives a stable trace identifier from the strongest existing canonical execution coordinate in this order:

1. exact `attempt_id`;
2. exact `run_id`;
3. exact `logical_operation_id`;
4. exact `operation_id`;
5. the event’s own `event_id`.

The derivation is a namespaced SHA-256 projection truncated to the OTel trace-ID width. It is evidence correlation only and grants no identity authority. Each event receives a deterministic span ID from trace coordinate + service + event name + event ID.

Consequences:

- P1 and P2 are separate Attempt traces;
- both may carry the same logical Job/operation attributes;
- no provider session is treated as the logical operation identity;
- multiple root spans in one trace are acceptable in V1 because the system does not invent causal parentage it did not observe;
- later W3C propagation is a separately reviewed wire-contract change, not an implementation shortcut.

### 7.6 Failure and absence semantics

Every investigation distinguishes:

- `OBSERVED`: the source emitted accepted evidence;
- `REJECTED`: a malformed or unsafe event was refused;
- `DROPPED`: the producer could not enqueue locally and continued;
- `UNAVAILABLE`: the evidence source or backend could not be queried;
- `STALE`: evidence exceeded its source-specific freshness bound;
- `ABSENT`: the query returned no matching evidence in its explicit window;
- `UNKNOWN`: evidence cannot resolve the question.

`ABSENT` is never “did not happen.” `UNAVAILABLE` is never healthy.

---

## 8. Privacy, security, and rights architecture

### 8.1 Never collect by default

- prompts;
- model responses;
- tool arguments or tool outputs;
- source-file bodies;
- patches or diffs;
- environment dumps;
- process command lines containing user content;
- HTTP request/response bodies;
- cookies;
- OAuth tokens;
- API keys;
- passwords;
- provider account email or personal metadata;
- raw Slack message text;
- full exceptions or upstream error bodies;
- arbitrary URLs;
- customer or portfolio data.

### 8.2 Error handling

Producers emit a closed `error_class` and, only where necessary, a reviewed bounded `error_code`. Free-form exception text is excluded from the runtime envelope.

Sidecar or collector messages derived from external systems must reuse `common.redaction.sanitize_external_text`. This program does not fork the redaction policy.

### 8.3 Socket boundary

Production uses launchd-owned Unix datagram sockets with separate per-principal paths and exact owner/group/mode settings. The Worker Broker’s `InitGroups=false` boundary is preserved; it is not added to a broad observability group.

The sidecar receives the launchd-activated sockets. Runtime processes can write only to their assigned socket. No model, prompt, worker request, or environment-controlled payload selects a socket path.

### 8.4 Collector and backend network boundary

- host Alloy listens only on loopback or Unix sockets for local ingest;
- remote export uses authenticated TLS over a private network or an authenticated proxy;
- Loki and Jaeger are not exposed directly to public networks;
- Grafana is behind SSO or a private access boundary;
- backend service accounts are least privilege;
- all images/binaries are version-pinned and digest-verified;
- no floating container tag, package launcher, or model-turn download is authoritative.

### 8.5 MCP boundary

The future observability MCP is not a generic Grafana grant. It must:

- use the existing `mastermind.executive_agent_capabilities/v3` owner;
- use HTTPS streamable HTTP;
- run mcp-grafana with writes disabled;
- use a least-privilege Grafana service account;
- expose only an exact reviewed read allow-list;
- pin server identity, version, and effective tool-schema/security-annotation digest;
- refuse schema drift;
- keep network access scoped to the exact MCP endpoint;
- provide no dashboard, alert, datasource, annotation, incident, mute, or other write tool;
- never become a path to Executive OS or backend administration.

---

## 9. Deployment topology and retention

### 9.1 Host side

One Alloy and one diagnostic sidecar per runtime host. Both are optional from the owning services’ perspective.

Alloy collects:

- sidecar OTLP traces and metrics;
- sidecar structured logs;
- existing control/worker/relay stdout and stderr files;
- launchd/process restarts where available;
- bounded CPU, memory, disk, filesystem, uptime, and network metrics;
- collector self-health.

A bounded persistent file queue may protect export across collector restart or network loss. It is a telemetry buffer, not an operation-delivery queue. Overflow drops telemetry according to explicit policy and cannot block or retry business work.

### 9.2 Diagnostics node

The initial diagnostics node is one separately failed Linux host or VM. It must not share the Mac control host’s failure domain.

Initial backends:

- Grafana Alloy v1.19.2 candidate;
- Prometheus v3.14.0 candidate;
- Loki v3.7.7 candidate;
- Jaeger v2.20.0 candidate;
- Grafana OSS v13.2.0 candidate;
- PostgreSQL supported stable release selected at implementation time;
- mcp-grafana v1.3.0 candidate for later MCP wave.

These are architecture-time observations, not install authorization. Every implementation carrier re-verifies current releases, licenses, checksums, vulnerability posture, and compatibility before pinning artifacts.

### 9.3 Initial retention budget

The first production configuration is deliberately bounded:

- metrics: 30 days, with explicit size ceiling and 15–20% free-disk safety buffer;
- logs: 14 days, with per-stream rate and burst limits;
- traces: 14 days, with total storage ceiling and service/event admission filters;
- collector queue: enough for a bounded network outage, never unbounded;
- Grafana metadata: PostgreSQL backup daily;
- no raw prompt/output retention because those data are never admitted.

Retention changes are operational decisions recorded through the existing durable owners. A backend silently running out of disk is a failed observability state, not an Executive failure.

---

## 10. Product journeys and failure states

### 10.1 Worker appears stuck

Starting from Job/Attempt/Worker identity, Sol sees:

- canonical current lifecycle state from Executive OS;
- last accepted diagnostic event and its source timestamp;
- claim/dispatch timing;
- broker request and response boundary;
- harness process/session start;
- provider turn start/collection phase;
- typed provider/network/error class;
- result-validation and projection phase;
- Agent Dialogue/Relay/Wake phase where instrumented;
- explicit gaps where instrumentation is not yet present.

The diagnosis names the first boundary with failure, staleness, unavailability, or an unexplained gap.

### 10.2 Mac/host crash

Remote evidence must survive long enough to answer:

- when the host stopped exporting;
- CPU, memory, disk, and process state before disappearance;
- which services disappeared together;
- which Attempt(s) were active by last observed correlation;
- whether launchd restarted services;
- which evidence was never exported because the local queue was lost;
- what recovered after reboot.

No conclusion that an Attempt failed or should retry is drawn from the host disappearance alone.

### 10.3 Provider failure

A controlled auth, 429, timeout, transport, or provider-process failure appears as typed diagnostic evidence on the provider/harness path. Executive retry law remains authoritative and independent.

### 10.4 Slack / Agent Relay outage

The relay path shows transport degradation while the underlying Job/Attempt remains whatever Executive OS says it is. A failed Slack post does not become a failed Job.

### 10.5 Safe P1 to P2 rollover

P1 and P2 remain separate Attempt traces. Both share the same logical child Job/operation attributes. The old provider surface is historical evidence and receives no current authority.

### 10.6 Slow system

Latency is decomposed across:

- admission and claim;
- capacity placement;
- broker connection and request;
- harness startup;
- provider inference;
- MCP/tool/network calls where safely instrumented;
- result collection and validation;
- terminal return projection;
- Agent Dialogue / Relay;
- Wake;
- Control Room composition.

### 10.7 Telemetry itself is broken

The UI and MCP surface report which evidence sources are unavailable or stale. Collector/backend failures are visible through self-health and dead-man signals. No stale-green state is allowed.

---

## 11. Wave graph

### OBS-F0 — architecture and current-source freeze

**Capability:** one durable architecture, capability ledger, collision map, semantic contract, topology, and wave plan.  
**State after merge:** `SPEC_ONLY / RECORDS_ONLY`.

### OBS-P0 — sealed-runtime-safe diagnostic seam

**Capability:** a real producer can emit one closed event nonblockingly to a real sidecar, which validates it, derives deterministic trace coordinates, and sends it to pluggable sinks without owning lifecycle state.  
**No existing service is instrumented or armed.**

### OBS-H0 — isolated host collection falsifier

**Capability:** Alloy tails synthetic and existing-format logs, gathers host metrics, receives sidecar OTLP, applies redaction/cardinality rules, persists a bounded queue, and survives collector restart in an isolated environment.

### OBS-D0 — diagnostics-node vertical

**Capability:** one synthetic Attempt journey appears in Prometheus, Loki, Jaeger, and a provisioned Grafana dashboard on a disposable isolated node with pinned artifacts and no public unauthenticated endpoint.

### OBS-I1 — Worker Broker / Operator Harness first real instrumentation

**Capability:** one real disposable Attempt produces a cross-boundary timeline from broker request through harness/provider collection, with telemetry disabled proving identical runtime outcome.

### OBS-L1 — relay, dialogue, and wake instrumentation

**Capability:** transport degradation and RESULT/Wake progression are diagnosable without changing their authority or retry semantics.

### OBS-C1 — Control Room diagnostic pointer

**Capability:** an existing runtime object shows bounded source-attributed diagnostic status and deep links without a competing cockpit or state rewrite. This starts only after current Control Room/Steward owners reconcile paths.

### OBS-MCP1 — attested read-only observability MCP

**Capability:** an authorized Sol can query bounded diagnostics through the existing capability registry; all writes and schema drift fail closed.

### OBS-R1 — retention, backup, upgrade, rollback, and DR

**Capability:** bounded storage, backup/restore, binary/image upgrade, rollback, collector outage, and node-loss procedures are independently proven.

### OBS-CANARY — real production acceptance

**Capability:** a fresh Sol diagnoses real and injected incidents from canonical object to repair decision, with measured MTTD and no manual multi-log archaeology.

---

## 12. First implementation wave contract

OBS-P0 owns only new source paths. Its observable mission is:

> Prove that a sealed-runtime-compatible producer can emit a bounded, secret-safe diagnostic event over a nonblocking Unix datagram boundary to an unprivileged sidecar, and that the sidecar can validate, normalize, correlate, count, and export that event through injected sinks while the producer remains unaffected when diagnostics are absent, full, malformed, or stopped.

Acceptance:

1. exact closed schema and vocabulary;
2. unknown fields fail closed;
3. prompts, outputs, environment, arbitrary attributes, and secret-shaped values cannot enter;
4. encoded packet never exceeds 8 KiB;
5. sender uses nonblocking Unix datagram I/O;
6. missing socket, permission error, full buffer, malformed path, or sidecar outage returns `False` and never raises;
7. sidecar refuses malformed/oversized/secret-bearing packets;
8. accepted packet receives deterministic trace and span coordinates;
9. metrics projection contains no high-cardinality IDs;
10. structured log projection retains exact correlation IDs and source attribution;
11. duplicate event ID is idempotently suppressed only in bounded process memory, with no durable lifecycle/store;
12. sidecar restart loses only process-local dedupe state and does not alter business work;
13. no current runtime, broker, harness, dialogue, relay, Wake, Control Room, capability registry, installer, or service file is modified;
14. focused tests, full repository test, compile, and diff checks pass;
15. independent adversarial review verifies authority, secret, backpressure, cardinality, and failure isolation.

Stop condition:

- stop after the P0 contract and sidecar are proven on their isolated branch;
- do not instrument a real Executive/Worker service, add external OTel dependencies, install Alloy, mutate launchd, or open a network port in this wave;
- return exact continuation handoff for OBS-H0 and OBS-I1.

---

## 13. Final production acceptance ruler

The program is not complete until all of the following are proven through real paths:

1. One real Attempt yields a queryable causal diagnostic path.
2. A controlled known failure is localized to the correct boundary.
3. Job, Attempt, and Worker correlation matches canonical Executive reads.
4. P1 and P2 remain separate Attempt traces linked to one logical responsibility.
5. High-cardinality identifiers never become metric labels.
6. Prompt, output, token, cookie, OAuth, API-key, and environment canaries are absent from every backend.
7. MCP write tools are unavailable and direct write attempts fail.
8. MCP tool-schema/security-annotation drift refuses capability admission.
9. Telemetry unavailable is rendered `UNAVAILABLE`, not healthy.
10. Telemetry fully disabled produces the same Executive/Worker outcome.
11. Slack/Relay outage is diagnosed as transport degradation, not Job failure.
12. No telemetry signal authorizes automatic retry, requeue, transfer, or completion.
13. A host crash leaves sufficient remote evidence for a useful postmortem.
14. Control Room pointers preserve canonical source attribution and never overwrite state.
15. Storage and queue growth are bounded, with stale-green/dead-man detection.
16. Install, upgrade, backup, restore, rollback, and disaster recovery are proven from exact artifacts.
17. A fresh Sol diagnoses a real incident without Chairman log archaeology.
18. Mean time to detection and diagnosis are measured against a manual baseline.
19. The correct Agent OS workstream, decision, discoveries, and handoff are current.
20. Final acceptance explicitly distinguishes green CI, merge, deployment, runtime evidence, and production proof.

---

## 14. No-rebuild boundaries

Do not create:

- another Job/Attempt/Worker/Event lifecycle;
- another operation or session identity plane;
- another scheduler, queue, retry table, or worker registry;
- another Control Room or Steward;
- another Agent Dialogue, Wake, or Slack task store;
- another redaction library;
- another MCP capability registry;
- another release/deployment truth store;
- another Agent OS workstream system;
- a generic incident-management platform inside this program;
- a universal log schema that absorbs domain-owner truth;
- an observability alert that directly mutates runtime state.

The program extends existing owners through bounded evidence adapters and read projections only.

---

## 15. Exact next action

Open OBS-F0 as a records-only PR from `sol/runtime-observability-f0-20260830` against protected `master`, require current-base reconciliation and hosted `test`, then stack OBS-P0 from the exact F0 head so implementation can begin without widening or bypassing the architecture carrier.
