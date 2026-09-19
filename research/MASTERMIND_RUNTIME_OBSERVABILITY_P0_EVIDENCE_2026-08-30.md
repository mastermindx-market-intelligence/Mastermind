# Runtime Observability Fabric P0 — Diagnostic Sidecar Evidence

**Evidence date:** 2026-09-18 / 2026-09-19 UTC  
**Capability:** `OBSERVABILITY SUBSTRATE BUILT`  
**Capability state:** `BUILT_NOT_PROVEN / PRODUCTION_INERT`  
**Carrier:** `sol/runtime-observability-p0-finish-20260918` / PR #843

This record closes Task 9 of
`docs/superpowers/plans/2026-08-30-runtime-observability-p0-diagnostic-sidecar.md`.
It records the verified isolated producer-to-sidecar substrate only. It does **not** claim
`EXECUTIVE FULLY OBSERVABLE`, deployment, production instrumentation, or backend telemetry proof.

## 1. Source identities

### Architecture dependency

- Original protected OBS-F0 basis:
  `28d365cceaef6efb0a26e0ac9af51ead44695d60`
- Original protected tree:
  `f55ab9d79b3ba5fa25bc090d3d7fa8a4ea4b0bf2`
- OBS-F0 architecture head:
  `c45839b2d175728a67238214ec40c768de25baa9`
- OBS-F0 protected merge through PR #277:
  `be4cb72c7c6c663ae7c09a7e2d22543ab406b027`

### P0 implementation

- Historical P0 carrier: PR #278 / `sol/runtime-observability-p0-20260830`
- Historical reconciled P0 head inherited by the fresh carrier:
  `38fa93a457a352aada58cb331884d1dae6e0818c`
- Current implementation semantic head verified in this evidence:
  `7b9fd796359f2b5752501a49b654461b82fb46f6`
- Semantic tree:
  `88082fcda41a21f5d456e97654a57166cca419f2`
- Protected master merged into the fresh carrier before semantic hardening:
  `20dc89a201b9dfa65c2b6a2366072f45d885cb5c`
- Protected master at release-readiness reconciliation:
  `55473bb43c3ae1908f53ddd4ccfe724643dd6c69`
- Current-master synthetic integration proof commit:
  `f0fd3811d7aa1c7c6aa47142b69564e57b6a0f22`
- Current-master synthetic integration tree:
  `87162bb82f933f7c5ae7e631583eeb06ee1e9d9f`

The four protected-master commits after `20dc89a...` are path-disjoint from every P0-owned
production/test path. Current protected procedure therefore permits review reuse for the unchanged
semantic head while requiring current integration proof. PR #843 is the sole live P0 source carrier;
PR #278 is preserved and closed as superseded historical contract/RED evidence.

## 2. Final P0 changed-path census

The P0 allow-list plus this evidence record is:

1. `common/runtime_diagnostics.py`
2. `integrations/runtime_observability/__init__.py`
3. `integrations/runtime_observability/contract.py`
4. `integrations/runtime_observability/sinks.py`
5. `integrations/runtime_observability/sidecar.py`
6. `scripts/runtime_observability_sidecar.py`
7. `tests/test_runtime_diagnostics_contract.py`
8. `tests/test_runtime_diagnostics_emitter.py`
9. `tests/test_runtime_observability_contract.py`
10. `tests/test_runtime_observability_sidecar.py`
11. `tests/test_runtime_observability_sinks.py`
12. `tests/test_runtime_observability_static_fences.py`
13. `research/MASTERMIND_RUNTIME_OBSERVABILITY_P0_EVIDENCE_2026-08-30.md`

No Executive lifecycle owner, Worker/Dialogue/Wake/Control Room owner, dependency manifest,
installer, launchd unit, workflow, credential, database, production service, or network-listener path
is modified by P0.

## 3. Immutable RED -> GREEN history

The historical P0 branch preserves test-first commits before implementation:

| Capability | RED receipt | GREEN receipt |
|---|---|---|
| closed runtime diagnostic contract | `fe80ff3321c3af0c6502d8e8037fad8d148b3a01` — `test(observability): define runtime diagnostic contract red` | `623046f49cce9b0014e82274088d4b6abb5ae5cf` — `feat(observability): add closed runtime diagnostic producer` |
| nonblocking Unix datagram emitter | `d0ca9321c65384d83c0f5b047d661fcfb957e924` — `test(observability): define nonblocking emitter red` | implemented by the producer commit above and carried through current hardening |
| deterministic normalization / trace-log-metric projection | `1cee27d87c53b05cccbdc8180ddce58434a0eb7d` — `test(observability): define sidecar normalization red` | `983bafc6e2e8642710fef8e815c0bbcbd14de62a` — `feat(observability): normalize diagnostic evidence` |
| isolated fixed sinks | `e9f72a4227974c83a3c7695034201f928d054bfe` — `test(observability): define isolated sink behavior red` | `e9447cc24a731337b5c5ffbc0558951c1a8b9202` — `feat(observability): add isolated diagnostic sinks` |
| bounded sidecar / dedupe | `6ca93edc665bad515c1c0b23f43e917fb493d543` — `test(observability): define bounded sidecar red` | `c70d2cc8de4f73b4fa662a8a05c6b557257b4154` — `feat(observability): add bounded diagnostic sidecar` |
| P0 authority + disposable CLI fences | `aa97dc89c554da1359b9fc1927c7a8dc9561dbdc` — `test(observability): define P0 authority and CLI fences red` | `29ffb01565c20b7d0dbe1d2b4a0db926dc0941e0` — `feat(observability): add disposable sidecar entrypoint` |

The first independent review on PR #278 then identified four bounded safety defects at
`24fecd44c0d72b7ccde55a071d2d6b6158eed37d`. The historical branch preserves the repair sequence:

- `3f614ae94a25585f81cd3b3f41016a79c19aa1cd` — RED tests exposing traversal/symlink and cleanup races.
- `31220960de0c6b2613cf390466f6d13f0214e06b` — GREEN disposable-path normalization and exact socket ownership.
- `82daf57adee1df5b6d35ac091cb938a1461fd4d7` — RED test requiring cleanup to remain anchored to a live receiver.
- `059752865e4210bec30e8921960afee165dc0603` — GREEN live-receiver cleanup anchoring.
- Current hardening commit `7b9fd796359f2b5752501a49b654461b82fb46f6` adds immutable event snapshots and broader ordinary-exception containment around socket setup/send/close while preserving process-control exceptions.

During the final hardening pass, newly discriminating local checks first produced four failures before
the implementation repair and then passed. That transient working-tree RED was not committed as a
separate immutable SHA, so this record does not pretend otherwise; the immutable RED history above
remains the audit source.

## 4. GREEN verification

### Exact semantic head `7b9fd796...`

- Focused six-file P0 suite: **108 passed**.
- Adjacent shared redaction/security verification: **55 passed**.
- Canonical repository gate on the clean Python 3.12 environment: **644 passed, 9 warnings**.
- `git diff --check`: pass.
- Python compile verification: pass.
- shell syntax validation: pass.
- Pinned Macro dependency used by the clean verification:
  `256c757b3c4f0ec759571c29a30a71387d0a18f8`.

### Current protected-master compatibility

Protected master advanced to `55473bb43c3ae1908f53ddd4ccfe724643dd6c69` without touching
any of the 12 semantic P0 paths. A synthetic merge produced
`f0fd3811d7aa1c7c6aa47142b69564e57b6a0f22` /
tree `87162bb82f933f7c5ae7e631583eeb06ee1e9d9f`.
The focused P0 suite passed on that synthetic integration with the semantic source unchanged.

A first local synthetic focused invocation hit macOS `AF_UNIX path too long` because the shared
host's pytest temp-counter path itself exceeded the Darwin Unix-domain socket pathname ceiling.
The same unchanged code passed with a bounded short pytest base directory. No product or test
relaxation was made.

GitHub PR #843 carries the authoritative hosted merge-context `test` gate. The evidence-file-only
commit that contains this record must receive a fresh exact-head hosted result before merge
adjudication.

## 5. Manual disposable canary

A fresh host-local canary was executed from the exact semantic head as the non-root workstation user.

Receipt:

```json
{"accepted_json_lines":1,"domain_result_identical":true,"domain_result_live":{"business_value":"unchanged","status":"SUCCEEDED"},"domain_result_stopped":{"business_value":"unchanged","status":"SUCCEEDED"},"euid":501,"event_id":"69bd4f7b-1dae-44c3-821b-b5248b27d6d3","event_sha256":"49d8e9cf5ee794466039e84d7b288b3c710f253fcf3c3e65dd830c93080cefc0","log_event_sha256":"49d8e9cf5ee794466039e84d7b288b3c710f253fcf3c3e65dd830c93080cefc0","log_span_id":"819df1bb3e7d798e","log_trace_id":"252c342d1f71e24894268972bb0f8600","metric_contains_correlation_value":false,"metric_labels":[{"environment":"test","event_name":"diagnostics.canary","evidence_source":"runtime-emitter","outcome":"SUCCEEDED","phase":"broker","service":"worker-broker","transport":"unix-datagram"}],"non_root":true,"producer_live_return":true,"producer_stopped_return":false,"schema":"mastermind.runtime_observability.p0_canary/v1","semantic_head":"7b9fd796359f2b5752501a49b654461b82fb46f6","sidecar_exit_code":0,"sidecar_summary":{"accepted":1,"duplicate":0,"rejected":0,"sink_failed":0,"source":"runtime-observability-sidecar"},"socket_mode":"0o600","socket_removed":true,"span_id":"819df1bb3e7d798e","trace_id":"252c342d1f71e24894268972bb0f8600"}
```

The canary proves:

- effective UID 501 / non-root execution;
- bound socket mode `0600`;
- live producer return `True`;
- exactly one accepted JSON line;
- canonical event SHA-256 equals the sidecar log projection;
- deterministic trace/span coordinates agree between parser and sidecar output;
- bounded metric labels contain no correlation identifier value;
- sidecar terminal summary is `accepted=1, rejected=0, duplicate=0, sink_failed=0`;
- sidecar exits cleanly and removes the exact owned socket;
- a second emit after the sidecar stops returns `False`;
- the domain-operation result is byte-for-byte semantically identical before and after diagnostic loss.

This was a disposable local proof only. It did not install, arm, deploy, expose a production listener,
or write a production telemetry backend.

## 6. Security, cardinality, authority, and failure-isolation findings

### Secret and input safety

- Secret-shaped correlation identifiers are rejected by the closed producer contract.
- Unknown schema keys, unknown correlation prefixes, unknown dimensions, oversized field counts,
  control characters, email-shaped values, filesystem paths, and URLs are rejected.
- Invalid UTF-8, malformed JSON, duplicate JSON keys, unsupported top-level fields, invalid schema,
  invalid dimensions, invalid duration shapes, and oversized packets are rejected before sink projection.
- Sink exception text is passed through the canonical external-text redaction helper and bounded.

### Cardinality

- Metrics include only bounded `service`, `event_name`, `outcome`, and closed dimension labels.
- Correlation identifiers remain trace/log coordinates and never enter metric labels.
- Sidecar counters use bounded reason classes.
- Dedupe is oldest-first bounded process memory with both entry and age ceilings; restart has no
  durable dedupe state.

### Authority

- Executive OS remains the sole Job/Attempt/Worker/Event lifecycle owner.
- P0 contains no lifecycle database, scheduler, queue, retry service, business mutation surface,
  generic network listener, model-facing writer, credential plane, or second publication authority.
- Static fences prohibit HTTP clients, SQLite/durable-state primitives, queue/retry vocabulary,
  business mutation vocabulary, and producer threading/sleep/file/TCP paths.
- The disposable CLI refuses root execution and accepts only bounded absolute Unix-socket paths under
  approved disposable roots.

### Failure isolation

- The producer sets the Unix datagram socket nonblocking before send and performs one send only.
- Missing, stopped, permission-denied, would-block, partial-send, socket-factory, send, and close
  failures return `False` and do not retry or persist.
- Ordinary diagnostic exceptions are contained; process-control `BaseException` is not swallowed.
- `CompositeSink` catches ordinary sink exceptions, including `TimeoutError`, records a bounded
  failure, and continues to later fixed sinks. It does not add threads, retries, or a timeout scheduler.
- One failing sink cannot stop a healthy fixed sink from receiving the event.
- Diagnostic success/failure/loss is directly tested to leave the owning domain result unchanged.
- Disposable socket setup rejects `..` traversal and symlinked caller-controlled ancestors.
- Cleanup is anchored to exact UID/device/inode/type plus the live bound receiver; a replacement
  socket is never unlinked.
- Process umask restoration is tested even when socket construction fails.

## 7. Capability truth and non-goals

### What is true after P0

`OBSERVABILITY SUBSTRATE BUILT`.

Mastermind has a sealed-runtime-safe stdlib producer contract, closed event validator,
nonblocking one-datagram emitter, deterministic diagnostic projection, fixed isolated sinks,
bounded non-authoritative sidecar state, and a disposable CLI that proves the vertical locally.

### What is not true

P0 is `BUILT_NOT_PROVEN / PRODUCTION_INERT`.

This carrier does **not**:

- install or arm a sidecar service;
- instrument Executive, Worker, Operator Harness, Dialogue, Relay, Wake, or Control Room owners;
- create a durable observability queue/store;
- provision Alloy, Jaeger/Grafana, OTLP credentials, or a production exporter;
- expose a Business MCP observability writer;
- create a TCP/HTTP listener;
- mutate Job/Attempt/Worker/Event lifecycle state;
- prove production backend ingestion/query;
- make Mastermind or Executive OS “fully observable.”

## 8. Exact continuation boundary

### OBS-H0

OBS-H0 owns **isolated Alloy collection and the persistent telemetry-export queue**. Any bounded
telemetry persistence/retry policy belongs there, never in the P0 producer or business lifecycle path.

### OBS-I1

OBS-I1 owns the **first real Worker Broker / Operator Harness instrumentation**. It may start only
after a fresh collision/source-owner re-check and must consume this P0 producer without transferring
Worker/Executive lifecycle authority.

Later production acceptance must separately prove service activation, real exporter/backend ingestion,
backend queryability, and failure injection showing sidecar/exporter loss still changes zero domain
outcomes.

## 9. Stop statement

**STOP at the isolated substrate.**

PR #843 and this evidence record authorize no install, arm, deploy, production credential,
production listener, Executive/Worker instrumentation, backend cutover, or lifecycle-state change.
Those effects require their own bounded successor carrier, current protected-source reconciliation,
and applicable production proof.

Do not create another diagnostics, lifecycle, retry, queue, state, identity, health, or publication
plane to continue this program.
