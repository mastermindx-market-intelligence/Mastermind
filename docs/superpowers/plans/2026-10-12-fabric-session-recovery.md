# Fabric session recovery implementation plan and frontier

**Goal:** Preserve logical Fabric workers/orchestrators across quota and context exhaustion, automatically triage safe stops, and visibly queue until qualified capacity exists without duplicating scheduler, router, memory or authority planes.

**Spec / runbook:** `docs/superpowers/specs/2026-10-12-fabric-session-recovery.md`; `docs/runbooks/fabric-session-recovery.md`.
**Source/procedure pin:** protected `25c4b7923734392b1013afae179966985819d847`.
**Operation:** `fabric-session-continuity-20261012-web-001`.
**Workspace:** `/Volumes/Mastermind/agent-workspaces/web/fabric-session-continuity-20261012-web-001`.
**Branch / PR:** `sol/web-fabric-session-continuity-20261012-web-001`, Mastermind #1367 (draft).
**Previously published implementation:** `5b12f8ef0bfa3fdb31822b921004368693762fa0`. The Git commit containing this cumulative frontier identifies the newer delta.

## Completed source increments

- [x] Positive non-modifying quota-release proof derived from existing Job/Attempt/checkpoint/grant/quota and immutable Events. Missing evidence is not release evidence.
- [x] Existing atomic COO retry accepts qualified `NON_MODIFYING_QUOTA`. Same logical Job, checkpoint, constraints and grant survive. Only the settled predecessor hold clears; the exhausted quota pool remains RATE_LIMITED. Existing TX9 stays intact.
- [x] Synthetic-provider / real-SQLite tests cover queue/reopen, alternate mock provider registrations, current-proof drift and thirty duplicate callbacks producing one requeue. These are not thirty distinct live workers or actual provider-migration acceptance.
- [x] Typed stop diagnostics distinguish quota/concurrency from authentication, safety/permission, approval, transport loss, semantic failure and unknown effects. Diagnostics never grant retry authority.
- [x] Context planning preserves response, tool and recovery headroom before admitting a new turn. Oversized next input returns `REBUILD_NEXT_TURN_CONTEXT`; compaction requires remeasurement before the next turn. Target-fit never drops mandatory state.
- [x] Existing private control service and CLI expose `session-recovery ROOT_JOB_ID --limit 1..500`, default 100, through unchanged kernel-peer authorization and READY gate. This is not Web/MCP enrollment or a mutation endpoint.
- [x] Queued-worker diagnostics retain the preceding requeue-bound Attempt, worker and quota-stop cause. Current versus previous stop scope is explicit. Queue position and ETA remain null without evidence from their existing owner.
- [x] Independent review completed and its exact result was consumed. Acceptance of the review task is not approval of source release.

## Verification and release blockers

Original published source: **311 passed**, zero failures/errors/skips. Retain this historical evidence; it does not cover the later interface/context delta.

Current-turn broad campaign: `test_executive_quota_rollover.py`, `test_executive_quota_rollover_runtime.py`, `test_executive_session_recovery.py`, `test_executive_session_recovery_client.py`, `test_executive_session_recovery_service.py`, `test_executive_os_sqlite.py`, `test_operator_continuity_projection.py`, `test_executive_service.py`: **515 cases: 510 passed, 5 failed, 0 errors, 0 skipped.** All failures are the review regressions below, retained as ordinary failing tests, not skipped/xfail. JUnit `research/evidence/fabric-session-recovery-reviewed-20261012.junit.xml`, SHA256 `ab5b01671c3aacd82385772ba5edbc4de034e85814ffce2ab6103c950a5da25c`.

After the final queued-stop diagnostic delta, the four affected Runtime/context/client/service test modules passed **83 cases, 0 failures/errors/skips**. JUnit `research/evidence/fabric-session-recovery-final-delta-20261012.junit.xml`, SHA256 `2e3da4a4135086f4fff4dd95ebd64d2d9912fc0ec8ddd526fde15872ab6b1eb4`. Broader unchanged service evidence was reused; no aggregate full-suite green claim. `py_compile` of changed implementation/client/service-test modules and `git diff --check` passed.

Five failing tests in `tests/test_executive_quota_rollover.py`:

1. `test_existing_operator_quota_owner_is_a_valid_typed_stop_producer`: canonical operator-authored JOB_RATE_LIMITED currently does not qualify.
2. `test_saved_receipt_does_not_reread_mutable_generation_state`: historical receipt reads depend on mutable generation rows.
3. `test_late_unknown_effect_does_not_erase_a_previously_committed_receipt`: later observations invalidate an old receipt read; fresh retry must remain blocked without rewriting accepted history.
4. `test_additive_event_column_does_not_invalidate_historical_proof`: hashing whole Event rows is brittle under an additive schema column.
5. `test_proof_json_uses_the_same_canonical_wire_as_runtime`: proof JSON parsing differs from Runtime canonical JSON.

## Review and effect custody

Review run `fabric-session-recovery-review-20261012-r1`, root/parent `fabric-session-continuity-20261012-web-001`, Grok 4.6 on Ubuntu 2. Packet SHA256 `52291c7cd4ae240772de1777da44638c6144c1118a8d7bf84be85a7b9960f328`. Retained result `<installed kit>/ext/lanes/fabric-session-recovery-review-20261012-r1.remote.stdout`: 8889 bytes, SHA256 `09640c705e494056f2a8f195be754adc801d12293a5060a79533affaa1bd52af`.

Original run completed rc=0 / signal=ok. Existing `fabric_task.py accept ... --by reviewer` applied once; readback is ACCEPTED / VALIDATED_OUTCOME with the original root and parent. No replacement reviewer was launched. No active worker/watcher obligation remains from this terminal review.

The reviewer found no breach of the stated live-writer, unknown-effect, modifying-grant or exhausted-pool fences, but identified the correctness defects above. A proposed quota-proof rewrite was blocked by the tool safety check before dispatch. Original-target readback confirmed no rewrite effect. Preparatory edits were rolled back; `git diff` verifies the quota implementation module equals the published version. That refused effect was not retried through another tool, carrier, worker, account or model. Independent diagnostic/client/context work continued. No modifying effect remains ambiguous.

An earlier combined retry-baseline command was also blocked before dispatch and was not replayed. It is not passing evidence. Typed publication previously succeeded on its original registered carrier after exact reconciliation; a failed precheck is not a blanket tool or repository denial.

## Remaining integration and acceptance

**State: PARTIAL / source candidate; release blocked.** No installed native kit, production Job, provider account, shared budget, model, concurrency limit, routing setting, watcher, service or grant was changed. Automatic recovery here is READ/RUN_TESTS-only; transparent continuation of modifying coding workers is not enabled.

- [ ] Resolve the five quota-review regressions under the actual permitted source-action boundary. Do not evade the recorded tool safety refusal. Reverify affected proof/receipt tests and obtain exact-head independent review before release.
- [ ] Compose #1365 model/host selection, #1253 shared-pool accounting and #1247/#1248 suitability/capacity. A provider/harness name is not equivalence or independent quota.
- [ ] Compose #1289 immutable continuation PREPARE/ACK and #656 source compilation. Successor must consume mandatory state and perform useful work, not merely have checkpoint bytes stored.
- [ ] Bind adapter-observed quota/context/concurrency stops and generation-bound checkpoint/release to actual Grok/GLM/Cursor/native routes. The account-local transport is a separate installed surface, not updated by this PR.
- [ ] Install reviewed diagnostics through normal release and project through the existing parent/UI bridge without new root access. Preserve #1344 exact native-parent return.
- [ ] Qualify same-model/different-pool and cross-provider continuation, shared-budget exclusion, all-slots-busy, reset/slot-return wake, cold restart, context rollover and original-parent consumption. Then qualify thirty distinct logical workers under one unchanged root grant.

## DO_NOT_REDO / next action

Do not redispatch the accepted review, overwrite native-kit/sibling source, reset exhausted quota to AVAILABLE, infer death from stream detachment, replay a modifying/unknown-effect worker, or claim installed fleet adoption. Reuse accepted evidence unless a relevant change affects it. Keep #1367 draft with ordinary failing regression evidence and this single cumulative frontier. The next critical source action is the blocked quota-proof/receipt correction, followed by exact-head review and the existing integration chain. Publishing the independent diagnostic delta is not mission completion.
