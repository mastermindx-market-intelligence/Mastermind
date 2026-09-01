# Runtime Observability Fabric — Current Source Reconciliation

**Observed:** 2026-08-30  
**Operation:** `mastermind-runtime-observability-fabric-f0-architecture-20260830-sol-001`  
**Protected Mastermind basis:** `28d365cceaef6efb0a26e0ac9af51ead44695d60`  
**Protected tree:** `f55ab9d79b3ba5fa25bc090d3d7fa8a4ea4b0bf2`  
**Skillpack:** `mastermind.sol_skillpack.v1` v1.0.1 / bootstrap-major 1  
**Macro main observed:** `ede7e065a90b294e9835e98e5326a84e1c14d038`  
**State:** `RECORDS_ONLY / SOURCE_RECONCILIATION`

---

## 1. Procedure receipt

The following canonical documents were loaded atomically from protected Mastermind commit `28d365cceaef6efb0a26e0ac9af51ead44695d60` before the F0 write:

- `docs/sol_skills/INDEX.md`;
- `docs/sol_skills/COLD_START.md`;
- `docs/sol_skills/RECONCILE_STATE.md`;
- `docs/sol_skills/COMMISSION_WAVE.md`;
- `docs/sol_skills/WORKER_AVENUE_ROUTING.md`;
- `docs/sol_skills/WATCHER_ACTION_LOOP.md`;
- `docs/EXECUTIVE_WORKER_ROUTING_CHAIRMAN_ADDENDUM.md`;
- `docs/EXECUTIVE_CHAT_NATIVE_SOL_HIERARCHY_LAW.md`;
- `docs/AGENT_DIALOGUE_SESSION_CLOSE_LAW.md`.

Compatibility passed because bootstrap major 1 satisfies the Skillpack minimum 1.

---

## 2. Existing runtime facts used by F0

### Worker Broker

`control_plane/executive_worker_broker.py` is an authenticated AF_UNIX broker that deliberately remains smaller than a scheduler/control plane. It exposes a closed typed operation set and no generic shell endpoint.

Current launch requests already carry:

- `run_id`;
- `job_id`;
- `worker_id`;
- workspace/run/result coordinates.

Current Operator Harness calls carry typed:

- operation ID;
- process generation;
- session epoch;
- turn reference;
- provider session handoff where required.

The handler frames exactly one bounded response after request identity is known, keeps full exception traces/values out of the socket, and preserves cancellation/shutdown semantics. The V1 observability design therefore does not widen this wire.

### Sealed process boundary

The current control and worker launchd templates execute Python with `-I -S -B`. This is a load-bearing sealed dependency boundary. The Runtime Observability design therefore does not import OTel SDK/exporter dependencies into those processes.

### Existing log seams

Current launchd templates already define separate bounded stdout and stderr paths for:

- Executive control;
- Worker Broker;
- Agent Relay.

These are valid initial collection seams and fallback evidence. They are not sufficient as the final semantic correlation contract.

### Remote host pattern

`ops/control_room_remote/mastermind-control-room-remote.service` establishes an existing hardened Linux/systemd read-projection pattern. It demonstrates that a failure-independent remote diagnostics node is compatible with the estate, but does not prove that the current host has capacity or that observability is deployed.

### Shared policy owners

- `common/redaction.py` owns bounded, secret-shape-aware sanitization for external text.
- `config/executive_agent_capabilities.json` and `control_plane/executive_agent_capabilities.py` own exact MCP transport, URL, server identity/version, enabled-tool, and effective tool-schema/security-annotation digest policy.

Observability reuses these owners rather than creating alternatives.

---

## 3. Collision census

### Open implementation collision: Mastermind PR #265

Title: `AD-RET1: bounded Executive terminal return projection`

Exact scope includes:

- `control_plane/executive_service.py`;
- `control_plane/executive_terminal_return.py`;
- corresponding tests.

Ruling:

- OBS-P0 does not edit `executive_service.py` or terminal-return paths;
- later result-projection instrumentation must reconcile after #265 is accepted, rejected, or superseded by canonical source.

### Open implementation collision: Mastermind PR #153

Title: `[DRAFT][HOLD-FOR-SOL] Worker Browser B1: isolated local Control Room review`

Exact scope includes current Control Room UI/server and Worker Browser paths.

Ruling:

- OBS-P0 does not edit Control Room or Worker Browser paths;
- OBS-C1 waits for current owner reconciliation before adding diagnostic pointers.

### Active semantic owners

The following are protected or active no-rebuild boundaries:

- Executive OS lifecycle and strict COO machinery;
- Operator Continuity Attempt/session/process law;
- Agent Dialogue V2 applicability and Attempt rollover;
- Agent Relay runtime/enrollment;
- Wake Fabric;
- exact Sol action-target resolver;
- Steward / Control Room composition;
- Capacity and provider identity/readiness;
- current terminal return projection.

No open PR containing `OpenTelemetry` was found. Searches for `observability` and `telemetry` returned broader records/continuity work, not a competing runtime observability implementation.

---

## 4. Macro / Agent OS census

At Macro commit `ede7e065a90b294e9835e98e5326a84e1c14d038`:

- no exact `mastermind-runtime-observability-fabric` Agent OS record was found;
- generic references to observability in unrelated decision records are advisory context only;
- the owning Agent OS workstream should be created after F0 acceptance/merge so its source-law reference is immutable and recoverable.

This F0 carrier does not create a parallel workstream store.

---

## 5. Current upstream observations

These are architecture-time candidate observations, not install authorizations. Implementation waves must re-verify current releases, licenses, checksums, advisories, and compatibility before pinning artifacts.

| Component | Observed current release | Initial ruling |
|---|---:|---|
| Grafana Alloy | `v1.19.2` | selected host collector candidate |
| Prometheus | `v3.14.0` | selected metrics backend candidate |
| Grafana Loki | `v3.7.7` | selected log backend candidate |
| Jaeger | `v2.20.0` | selected initial trace backend candidate |
| Grafana OSS | `v13.2.0` | selected human diagnostics candidate |
| mcp-grafana | `v1.3.0` | later read-only MCP candidate |
| Grafana Tempo | `v3.0.3` | deferred initial deployment; future scale option |

Primary upstream repositories:

- `https://github.com/grafana/alloy`;
- `https://github.com/prometheus/prometheus`;
- `https://github.com/grafana/loki`;
- `https://github.com/jaegertracing/jaeger`;
- `https://github.com/grafana/grafana`;
- `https://github.com/grafana/mcp-grafana`;
- `https://github.com/grafana/tempo`.

### Tempo 3 correction

The inherited seed assumed a simple Tempo single-node first deployment. Current Tempo 3 documentation/release architecture requires a Kafka-compatible queue and positions monolithic/local modes for local, testing, or small-scale use rather than the selected production topology. Adding a new queue and object-storage/distributed trace stack at current Mastermind volume would be disproportionate and would introduce unnecessary operational state.

F0 therefore selects Jaeger 2 all-in-one + Badger for modest initial trace volume and preserves OTLP as the backend-neutral producer contract. Tempo remains a later evidence-gated migration.

### mcp-grafana boundary

Current mcp-grafana supports write-tool removal, but query-language tools remain available. A future grant therefore requires both:

- upstream write disablement;
- Mastermind’s own exact enabled-tool allow-list and schema/security digest.

No MCP grant is created by F0.

---

## 6. F0 path census

F0 owns exactly four records paths:

1. `research/MASTERMIND_RUNTIME_OBSERVABILITY_FABRIC_F0_ARCHITECTURE_2026-08-30.md`;
2. `docs/superpowers/specs/2026-08-30-mastermind-runtime-observability-fabric-design.md`;
3. `docs/superpowers/plans/2026-08-30-runtime-observability-p0-diagnostic-sidecar.md`;
4. `research/MASTERMIND_RUNTIME_OBSERVABILITY_FABRIC_CURRENT_SOURCE_RECONCILIATION_2026-08-30.md`.

No implementation, dependency, workflow, runtime, service, installer, configuration, host, credential, database, Slack, Linear, Agent OS, or production path differs from protected master in F0.

---

## 7. Movement and release gate

Before F0 merge:

1. re-read protected `master`;
2. reload `docs/sol_skills/INDEX.md` and required skills if protected moved;
3. compare protected base to F0 head;
4. prove exactly the four records paths above;
5. inspect all new open PRs for path/semantic collisions;
6. require hosted `test` on the exact candidate head;
7. perform fresh Sol source/architecture review;
8. merge only with an expected-head guard.

Merge makes architecture durable only. It does not install, arm, deploy, or prove observability.

OBS-P0 may be developed as a stacked branch from the exact F0 head, but it remains a separate logical child/carrier and cannot be merged before its architecture dependency is canonically reconciled.
