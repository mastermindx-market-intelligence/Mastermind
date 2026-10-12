# Fabric session recovery implementation plan and frontier

> Execute inline through the existing Executive owners. Checkpoints are saves, not stops.

**Goal:** Preserve logical worker Jobs through quota and context pressure; make safe stops automatically requeue and expose actionable original-root diagnostics without duplicating the scheduler/router/memory planes.

**Spec:** `docs/superpowers/specs/2026-10-12-fabric-session-recovery.md`

**Source:** protected master `25c4b7923734392b1013afae179966985819d847`; managed operation `fabric-session-continuity-20261012-web-001`; branch `sol/web-fabric-session-continuity-20261012-web-001`.

## Completed source increments

- [x] Add `control_plane/executive_quota_rollover.py`: derive positive non-modifying quota release material from existing immutable Events, current Attempt/Job/checkpoint, quota hold and all predecessor generations. Missing evidence is not release evidence.
- [x] Wire material into `_retry_safety_material` and the existing atomic `commit_coo_retry_decision`. Keep the original Job/checkpoint/grant/constraints, clear only the settled predecessor capacity hold and retain RATE_LIMITED on the exhausted pool. Preserve the original TX9 path.
- [x] Validate command-aware historical quota requeue receipts against immutable predecessor source after a successor has claimed the Job. Concurrent duplicate calls reconcile one existing command.
- [x] Add `control_plane/executive_session_recovery.py`: typed adapter-stop diagnostics, measured context budgeting, target-context fit without mandatory-state truncation, and one bounded original-root triage snapshot.
- [x] Test first: absent producer/diagnostic APIs and the unreachable valid quota classifier were observed RED. Adverse JSON/frontier cases were also observed RED before fixes.
- [x] Final source verification: **311 passed**, zero failures/errors/skips, using the three new test modules plus `test_executive_os_sqlite.py` and `test_operator_continuity_projection.py`. The test suite used real Executive SQLite transactions and synthetic provider release observations. No live provider execution is established by these tests.

## Boundaries that remain intact

The legacy/native adapter installation is unchanged. No production Jobs, provider accounts, grants, shared budgets, models, concurrency limits, routing configuration, watchers or services were changed. This increment is READ/RUN_TESTS-only recovery; it does not enable transparent recovery of modifying coding workers. It does not turn Cursor into a model-equivalence category or infer that same-provider models have independent quota. It does not make the inert COO CLI an execution owner. The admitted dispatcher remains necessary for actual placement.

The initial combined retry-baseline command was platform-blocked before dispatch and was not replayed. A typed Git status precheck returned REFUSED/NOT_APPLIED; source workspace status independently confirms the registered operation and source path. These are not successful test/publication receipts.

## Independent review carrier

One bounded read-only Fabric review was admitted for `fabric-session-recovery-review-20261012-r1`, original root/parent `fabric-session-continuity-20261012-web-001`, selected Grok 4.6 on Ubuntu 2. Packet SHA256: `52291c7cd4ae240772de1777da44638c6144c1118a8d7bf84be85a7b9960f328`. This is review of exact source bytes, not permission to modify or deploy them. Reconcile this original run before any replacement review request. Result/acceptance remains pending until its exact result is consumed.

## Next integration work under existing owners

- [ ] Bind the typed stop observations and generation-bound checkpoint/stop producer to the actual installed Grok/GLM/Cursor/native adapters. Never reinterpret auth/safety/permission refusal or a detached stream as quota/death.
- [ ] Compose #1365 pinned/auto model-host selection with #1253 pool-family accounting and #1247/#1248 qualification/capacity. Prefer another eligible independent pool for the same model, then a qualified model for the same task. Exclude every route sharing an exhausted budget scope. Revalidate eligibility and reserve atomically through the current owner.
- [ ] Compose #1289 immutable PREPARE/ACK and #656 source compilation. Demonstrate that a successor actually consumes the portable frontier and performs useful work; retained database bytes alone are not consumption. Keep #1344 exact native-parent return semantics.
- [ ] Expose `project_root_recovery(runtime, root_job_id)` through an existing authenticated, root-scoped Executive read entry point and its current UI projection, without modifying the canonical mutation receipt wire or adding a second queue.
- [ ] Qualify context measurements and native compaction per adapter. Use the existing checkpoint INTENT/APPLIED boundary; rotate only from a durable mandatory frontier when compaction cannot fit.
- [ ] After required source review/CI and normal release: run admitted same-model/different-pool, different-provider, shared-quota, all-slots-busy, reset/wake, context rollover, cold restart and original-parent-consumption canaries. Then test the 30-logical-worker scenario under one unchanged root capacity grant.

## DO_NOT_REDO / effect custody

Reuse the 311-case evidence unless a relevant source or behavior changes. Do not overwrite the account-local native kit or another branch, re-dispatch the review run, fabricate a provider acceptance receipt, release an exhausted quota to AVAILABLE, or restart an unknown-effect predecessor. No live fleet-wide rollover or all-account installation is claimed. Preserve this workspace and its review obligation until publication/recovery references and the child result are reconciled.
