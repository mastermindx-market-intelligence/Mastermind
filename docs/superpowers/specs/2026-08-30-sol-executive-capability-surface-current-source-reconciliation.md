# Sol Executive Capability Surface — Current-Source Reconciliation

**Date:** 2026-08-30  
**Operation:** `mastermind-sol-executive-capability-surface-f0-20260830-sol-001`  
**Status:** `CURRENT_SOURCE_RECONCILIATION / SPEC_ONLY / RECORDS_ONLY`  
**Prior F0 basis:** `Mastermind@28d365cceaef6efb0a26e0ac9af51ead44695d60`  
**Current protected basis:** `Mastermind@be4cb72c7c6c663ae7c09a7e2d22543ab406b027`  
**Current Skillpack:** `mastermind.sol_skillpack.v1` v1.0.1 / bootstrap-major 1, loaded atomically from current protected source  
**Current-source movement:** Runtime Observability Fabric F0, Mastermind PR #277 / merge `be4cb72c7c6c663ae7c09a7e2d22543ab406b027`  
**Precedence:** this reconciliation controls where the parent SECS design/program could overlap Runtime Observability, generic operations health, a future diagnostic MCP, or the exact F0 changed-path census. All other parent architecture remains controlling.

---

## 1. Why reconciliation was required

SECS F0 was authored and placed on its sole branch while protected Mastermind remained `28d365c…`. Before its PR was opened, protected master advanced by one exact records-only merge: Runtime Observability Fabric F0.

The new protected source establishes a stronger and more specific owner for failure-independent runtime diagnostics:

```text
sealed runtime diagnostic event
-> nonblocking Unix datagram producer
-> unprivileged diagnostic sidecar
-> collection/redaction/bounded telemetry delivery
-> Prometheus / Loki / Jaeger / Grafana evidence services
-> attributed Control Room pointers
-> later attested read-only observability MCP
```

That movement is path-disjoint from the SECS records and from the planned pure GitHub release-evidence core, but it is semantically material to the broad `OP-A1` operations-observability language in the initial SECS design. A current-source amendment is therefore required before F0 release or any dependent branch is created.

No reset, rebase, force update, replacement branch, duplicate operation or blind continuation is permitted. The same SECS F0 carrier must preserve its history and reconcile current protected source.

---

## 2. Runtime Observability is the sole diagnostic evidence owner

Runtime Observability Fabric now exclusively owns the cross-runtime diagnostic evidence architecture for:

- sealed-runtime-compatible event emission;
- diagnostic sidecar validation and normalization;
- trace, log and metric derivation;
- diagnostic transport, collection, redaction and bounded telemetry delivery;
- observability backend selection and operation;
- correlation from canonical runtime identities to diagnostic evidence;
- absence/staleness/degradation semantics for telemetry;
- future Control Room diagnostic pointers;
- any future read-only observability MCP over those diagnostics;
- incident-detection and diagnostic-learning evidence under its own promotion law.

SECS must not create, copy or commission another:

- runtime diagnostic envelope;
- logging/metrics/tracing facade;
- telemetry sidecar or collector;
- diagnostic queue or buffer;
- Prometheus/Loki/Jaeger/Grafana stack;
- observability MCP;
- service/host diagnostic graph;
- incident evidence store;
- runtime-health truth store.

Runtime Observability remains evidence only. Executive OS still owns lifecycle, retry/requeue and current execution; Agent OS owns organizational state; Capacity owns placement; RuntimeBinding owns the current exact reasoning surface; GitHub owns implementation/CI truth. SECS does not widen Runtime Observability into any of those roles.

---

## 3. `OP-A1` is superseded by an integration wave

The parent SECS documents used the provisional label:

```text
OP-A1 — operations observability
```

That label and any wording that could authorize a generic SECS health backend, cross-service diagnostic schema, observability app, or runtime telemetry implementation are superseded.

The replacement is:

```text
OBS-I1 — Sol capability-surface integration with accepted Runtime Observability evidence
```

### OBS-I1 observable mission

Once the Runtime Observability owner has accepted production evidence and an attested read boundary, let Steward, capability introspection, the Sol plugin and Control Room consume its source-attributed diagnostic facts and pointers without copying telemetry or storing a parallel health state.

### OBS-I1 permitted work

- versioned client/adapter integration to the accepted Runtime Observability read contract;
- projection of `AVAILABLE`, `DEGRADED`, `STALE`, `UNAVAILABLE`, `EVIDENCE_INCOMPLETE` and exact diagnostic references;
- linking an exact Job/Attempt/Worker/operation/service/host fact to the first stalled or failed diagnostic boundary;
- compact rendering and drill-down in Chat/Control Room;
- prompt-injection-safe summarization by Sol over inert structured evidence;
- capability-health composition that preserves source owner, observation time and completeness.

### OBS-I1 forbidden work

- new telemetry collection, storage, indexing or retention;
- direct querying of raw backend databases when the accepted facade is unavailable;
- new runtime instrumentation;
- lifecycle mutation or automated retry from telemetry;
- model-authored health state;
- a second read-only observability MCP;
- a generic `service_health` implementation backed by SECS-owned state;
- hidden last-good health when current telemetry is absent.

OBS-I1 remains dependency-gated behind Runtime Observability's own accepted read capability and real proof. It is not an implementation child of SECS F0 today.

---

## 4. GitHub runner observability remains distinct and coordinated

SECS GH-A4 remains valid, but its authority is narrowed explicitly.

GitHub is canonical for GitHub Actions resources such as:

- workflow run and job state;
- required runner labels;
- runner ID, group, repository scope and GitHub-reported online/offline/busy state;
- queue-to-label-to-eligible-runner relationships;
- GitHub-reported runner software/version metadata where available.

Therefore GH-A4 may build a read-only GitHub Runner Observatory over exact GitHub API facts. It must not become a general host/service/process observability system.

Runtime Observability may later supply attributed runtime/host diagnostic evidence for the same incident, but the owners remain distinct:

```text
GitHub runner/job/label/queue fact       -> GitHub / GH-A4 evidence facade
runtime process/service/host diagnostics -> Runtime Observability
placement and worker realm suitability    -> Capacity / Model Router
Job/Attempt/Worker lifecycle               -> Executive OS
```

A future Sol composition may join these facts by exact identifiers and source references. Neither source overwrites the other, and the join creates no new canonical runner or host state.

GH-A4 must not:

- install instrumentation on runners;
- scrape arbitrary processes or files;
- create its own host heartbeat;
- infer host health from job count alone;
- register/delete/retag runners;
- perform Capacity reassignment;
- duplicate OBS dashboards or backend storage.

---

## 5. Capability introspection is composition, not observability ownership

The SECS capability-introspection result remains valid only as a current read projection over existing owners.

For diagnostic health, it consumes Runtime Observability when that source is accepted and available. For app authentication/scope it consumes the app/auth owner. For GitHub actions it consumes GitHub. For Executive state it consumes Executive OS. For current surface identity it consumes RuntimeBinding/SessionTarget and exact action-target evidence.

Capability introspection may report:

```text
AVAILABLE
AVAILABLE_WITH_CONFIRMATION
READ_ONLY
DEGRADED
AUTHENTICATION_REQUIRED
NOT_INSTALLED
SCOPE_MISSING
OWNER_NOT_PROVEN
PRODUCTION_DISARMED
EFFECT_UNKNOWN_HOLD
```

It stores none of these as independent truth and may not synthesize `AVAILABLE` from the absence of diagnostic errors.

---

## 6. Administrative actions remain separate from diagnostics

The parent provisional `OP-A2` concept is renamed:

```text
IA-A1 — exact infrastructure administrative actions
```

IA-A1 is not a child of Runtime Observability and does not derive authority from a health alarm. It is a family of separately reviewed owner-specific actions, each with its own principal, fixed target class, precondition, effect semantics, rollback and approval boundary.

Examples may include one exact service restart, tunnel-generation change or runner administration operation only after an accepted endpoint-specific design. There is no generic operations actuator or `repair(health_finding)` tool.

Telemetry may support a human/Sol repair decision, but it never initiates, authorizes, retries or verifies a lifecycle/admin mutation by itself.

---

## 7. GH-A1 remains current-safe

The first SECS implementation child remains:

```text
mastermind-sol-github-evidence-a1-20260830-sol-001
```

Its three planned paths are disjoint from Runtime Observability F0 and P0:

```text
integrations/mastermind_github_evidence/__init__.py
integrations/mastermind_github_evidence/release_gate.py
tests/test_mastermind_github_release_gate.py
```

GH-A1 is a pure, network-free, deterministic GitHub release-evidence computation. It imports no Runtime Observability source, emits no telemetry, installs no service, creates no app, performs no GitHub mutation and owns no runtime health fact.

The protected movement therefore changes GH-A1's stack base and source receipt, not its feature contract. Its implementation branch must be created from the exact reconciled SECS F0 head after this branch incorporates protected `be4cb72c…` history-preservingly.

---

## 8. Revised wave vocabulary

The controlling SECS wave list is now:

```text
SECS-F0  architecture, capability ledger and current-source reconciliation
GH-A1    pure deterministic GitHub release-evidence core
GH-A2    authenticated read-only GitHub evidence adapter
GH-A3    GitHub/path/operation collision census
GH-A4    GitHub runner observatory, GitHub facts only
BSC-P2   app-bound plugin generation after existing package/app gates
ST-A1    accepted Steward read app
EX-A1    bounded Executive app
SF-A1    exact Surface read projection
SF-A2    governed provision/rotate/retire actions
FL-A1    semantic child commission and fleet view
OBS-I1   consume accepted Runtime Observability evidence; no duplicate backend/app
IA-A1    separately gated exact infrastructure administrative actions
CR-A1    integrated Chat/Control Room composition
EC-A1    economics and learning instrumentation
CANARY   staged real multi-program proof
```

Where the parent design/program says `OP-A1`, read `OBS-I1` with the narrowed integration semantics above. Where it says `OP-A2`, read `IA-A1` with the separate administrative-action semantics above.

---

## 9. Revised F0 changed-path and capability truth

The same SECS F0 carrier now contains exactly four records-only paths:

1. `docs/superpowers/specs/2026-08-30-sol-executive-capability-surface-design.md`
2. `docs/superpowers/specs/2026-08-30-sol-executive-capability-surface-current-source-reconciliation.md`
3. `docs/superpowers/plans/2026-08-30-sol-executive-capability-surface-program.md`
4. `docs/superpowers/plans/2026-08-30-sol-github-release-evidence-a1.md`

This four-path census supersedes the parent program's earlier three-record F0 acceptance wording.

Current truth:

```text
Runtime Observability F0                     PROTECTED / SPEC_ONLY
Runtime Observability P0                     TESTS_RED / NOT_BUILT on separate carrier
SECS architecture + reconciliation           SPEC_ONLY / RECORDS_ONLY
GH-A1 local candidate                        BUILT_NOT_PROVEN / NOT YET PUBLISHED
all SECS apps, runner view and actions        NOT_BUILT unless separately listed in parent ledger
```

No runtime, app, MCP server, OAuth client, credential, GitHub action, runner action, Executive state, Agent OS state, Slack, Linear, host, telemetry, deployment or production capability is created by this reconciliation.

---

## 10. Exact next action

History-preservingly compose current protected `Mastermind@be4cb72c7c6c663ae7c09a7e2d22543ab406b027` into the same SECS F0 branch while preserving only the four exact records above as its delta.

Then:

1. verify protected-to-head is ahead-only, `behind_by=0`, exact four records;
2. open the sole SECS F0 draft/HOLD carrier against protected `master`;
3. stack GH-A1 from that exact reconciled F0 head;
4. publish only the three pure implementation/test paths;
5. run hosted exact-head proof and independent review;
6. do not start GH-A2, OBS-I1, IA-A1, app publication or any production action from F0/GH-A1 existence alone.
