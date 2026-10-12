# Fabric session recovery — cumulative implementation frontier

**Mission:** Preserve logical Fabric workers/orchestrators through quota and context exhaustion, automatically triage qualified recoverable stops, and visibly queue for equivalent capacity. Executive remains the only Job/Attempt/Event/queue/retry owner; existing Capacity, Agent OS, GitHub and provider adapters retain their responsibilities.

**Protected source/procedure:** `25c4b7923734392b1013afae179966985819d847`, compatible skillpack 1.0.1/bootstrap 1.
**Operation:** `fabric-session-continuity-20261012-web-001`.
**Workspace:** `/Volumes/Mastermind/agent-workspaces/web/fabric-session-continuity-20261012-web-001`.
**Branch / PR:** `sol/web-fabric-session-continuity-20261012-web-001`; Mastermind #1367, draft/hold.
**Prior published head:** `271d713af516a448542a082998e7ea97479cafea` (core increment `5b12f8ef0bfa3fdb31822b921004368693762fa0`). The commit containing this frontier binds the new source delta.
**Design / runbook:** `docs/superpowers/specs/2026-10-12-fabric-session-recovery.md`; `docs/runbooks/fabric-session-recovery.md`.

## Verified capability delta

1. Existing positive non-modifying quota proof makes atomic same-Job COO requeue reachable. Job/checkpoint/grant/constraints survive; only the settled predecessor hold clears; exhausted quota stays RATE_LIMITED. Unknown effects, live writers, modifying grants and exhausted allowance remain held. No second queue or memory store.
2. Existing authenticated private control-socket `session-recovery ROOT_JOB_ID --limit 1..500` retains its unchanged request boundary. First-page response now includes original-root state, total children, remaining attempts, parent/role, current registered provider/model/pool, previous pool's current status and historical stop cause. Registration is explicitly not served-model proof or capacity eligibility. Queue position/ETA stay unknown.
3. Pure read library supports root-bound `after_job_id` keyset pagination: LIVE_KEYSET (not a frozen cross-call snapshot), next cursor, returned-set counts and root event watermark. Tests cover 30 distinct records, foreign/root/malformed cursors and empty tail. **Socket/CLI cursor integration is not implemented**, see held action. Existing first-page socket returns all 30 fixture workers with richer fields.
4. Pool-reset-versus-busy behavior uses real disposable Runtime release/claim calls: previous pool can now be BUSY while original Job stays queued and its quota-stop history survives. Observation grants no restart permission.
5. Real-owner checkpoint-consumption test starts a generation, commits generation-bound checkpoint, uses the existing typed legacy release API, requeues the same Job, reopens Runtime, then dispatches a successor through the real supervisor. The model substitute reads the actual production prompt callback, asserts exact frontier and READ-only grant, derives its result from the saved next action and receives one result seal. Original pool stays RATE_LIMITED. **Provider/process observations are simulated: stronger than seeded database rows, not a real paid-model migration or original-parent wake proof.**
6. New `control_plane/codex_context_projection.py` maps exact-thread/turn `thread/tokenUsage/updated` into a closed numeric observation for the existing context planner. Uses last.totalTokens, not cumulative spend or double-added cache/reasoning components. Invalid/missing counts/windows stay UNKNOWN; no prompt/provider extras or native IDs escape; no assumed auto-compaction threshold. **Not adapter-integrated or installed.** Incumbent consumer is #1340's existing event normalizer; no duplicate adapter/event store.
7. Context planner preserves response/tool/recovery headroom, detects input that cannot fit after compaction, requires remeasurement and never drops mandatory portable state.

## New default-path integration gap

`OperatorHarnessOrchestrator.graceful_stop` → `ExecutiveOperatorHarnessPort.graceful_stop_operator_generation` → `apply_generation_operation` emits `OPERATOR_OPERATION_APPLIED`. Quota proof requires legacy `OHF_GRACEFUL_STOP`. Actual modern-stop test proves checkpoint/release observations survive but automatic quota requeue correctly stays held because recognized proof is absent. Do not manufacture a legacy event or reroute production stops to make it green. This gap is additional to the five original quota correctness defects.

## Latest verification

**270 tests: 263 passed, 7 failed, 0 errors/skips.** Expanded campaign covers quota/Runtime, context/triage, paging, successor consumption, socket/client, numeric telemetry and the complete existing `test_executive_operator_supervisor.py`. Seven ordinary failures remain: five original quota regressions plus two unimplemented cursor-transport tests. No full-suite green or release acceptance.

- `research/evidence/fabric-session-recovery-expanded-20261012.junit.xml`: SHA256 `2004b272d2a08f3929889561ccd6a93a9545f96817b13355d74962f54a5cac46`.
- `research/evidence/fabric-session-recovery-consumption-20261012.junit.xml`: **3 passed**, SHA256 `77062696c3796cbff75e79c68f388847e5ba86e59b22a4f39a45f2ad4018f47b`.
- `research/evidence/fabric-session-recovery-library-20261012.junit.xml`: **79 passed**, SHA256 `78adc242014e23561454b02f500036d93144029520cab4cfd50069ce66c7d8b9`.

Counts overlap; never add them. Earlier 311-pass, 515-case/5-failure and 83-pass evidence is historical. Missing APIs were RED before implementation; contradictory context totals were RED before their guard. `py_compile` and `git diff --check` passed. Diff proves quota implementation, Runtime mutation code, service/client request handlers and native Codex adapter unchanged from 271d713.

## Held actions and regressions

**Quota-proof correction:** prior typed rewrite blocked by tool safety check before dispatch; readback showed no effect; preparatory edits restored. `executive_quota_rollover.py` SHA256 remains `5fb0fe165657fd423c3bc5399cf2f9a61fd244b3ff2e5cd15ae68f1de3e1b152`. No alternate-carrier/worker/account/model retry. Five tests in `test_executive_quota_rollover.py` remain failing:

- `test_existing_operator_quota_owner_is_a_valid_typed_stop_producer` — canonical operator excluded.
- `test_saved_receipt_does_not_reread_mutable_generation_state` — historical receipt depends on mutable rows.
- `test_late_unknown_effect_does_not_erase_a_previously_committed_receipt` — later observations invalidate prior receipt reads, not only future execution.
- `test_additive_event_column_does_not_invalidate_historical_proof` — whole-row hashing is brittle.
- `test_proof_json_uses_the_same_canonical_wire_as_runtime` — loader differs from Runtime canonical wire.

**Socket cursor integration:** current continuation's `edit_block` to accept optional `after_job_id` was blocked by tool safety check before dispatch. Exact service readback proves no effect. No retry/alternate endpoint/worker handoff. CLI does not advertise unsupported flag. `test_session_recovery_client_can_request_the_next_worker_page` and `test_worker_paging_roundtrips_through_original_control_socket` remain ordinary failures, not skip/xfail. Existing first-page endpoint and independent library work are unaffected.

Earlier combined baseline test command was blocked before dispatch and not replayed. No modifying effect is ambiguous. A new chat/mode/general resume does not clear refusal. Updating this cumulative frontier initially required explicit rewrite mode; the tool invited schema correction, exact target was reread, and explicit rewrite was used. That technical schema recovery is distinct from the held safety denials.

## Review and parallel source custody

Original review `fabric-session-recovery-review-20261012-r1` (Grok4.6/Ubuntu2), same root/parent, was consumed/accepted once. Result8889 bytes SHA256 `09640c705e494056f2a8f195be754adc801d12293a5060a79533affaa1bd52af`; packet SHA256 `52291c7cd4ae240772de1777da44638c6144c1118a8d7bf84be85a7b9960f328`. Acceptance is of review task, not release. No active review/watcher remains; do not redispatch it.

#1340 head `3b231e6cc273315ac4a279f9793a9a9419de0460` owns current Codex adapter/tests. #1344 head `230cc186dcf49e618bcaed15ae2a449905b26f2a` owns native-supervisor continuation. Neither edited here. New numeric helper is an independent dependency, not integrated capability. #1289 head `9b7318baeb63399bd264bfb4fad2bd1617fff61c` owns PREPARE/ACK; #656 head `9a461ee416437f5b8591154f00b608e9b0ce0a32` owns source compilation. #1365/#1253/#1247/#1248 retain selection/economics/capacity.

## Remaining acceptance / exact frontier

**PARTIAL, SOURCE CANDIDATE, RELEASE HELD.** No native-kit, production Job/provider/budget/model/concurrency/routing/service/grant changed. No real paid-model transition or production compaction claimed.

Resolve actual source-action permission for held corrections, never bypass denials. Existing owners must compose modern stop receipts, immutable continuation/ACK, qualified model/pool selection and shared-budget accounting. Integrate the independent numeric helper only within incumbent adapter current-turn normalization, preserving helper/completion/generation scope and event ownership; unit tests do not prove installed telemetry.

Obtain exact-head review/CI and normal release; demonstrate actual same-model/different-pool and cross-provider useful continuation, shared quota exclusion, all-slots-busy, reset/return wake, context rollover, restart and original-parent consumption. Then qualify 30 distinct paid workers under unchanged root capacity.

**DO_NOT_REDO:** reuse accepted evidence unless affected; keep seven failures visible; preserve held/parallel source; never invent available quota or replay unknown work; never label library paging a socket feature, or test-adapter consumption a live provider result. Checkpoints/publication are saves, not mission completion.
