# Persistent Fabric workers: recovery and triage

## Release state

Source candidate: Mastermind PR #1367, operation `fabric-session-continuity-20261012-web-001`, protected procedure pin `25c4b7923734392b1013afae179966985819d847`.

**Not installed or production-proven.** The candidate adds safe non-modifying quota requeue through existing Executive owners and a bounded private control-socket diagnostic. The account-local `fabric_task.py` transport is not automatically upgraded by this PR. Modifying coding workers, real provider migration, automatic shared-pool accounting and original-parent successor consumption still require their existing integration and acceptance gates. Known quota-review regression failures keep release blocked.

## The durable identity

The existing Executive Job is the logical worker. Root, parent, objective, constraints, grant, accepted work and checkpoint survive. A provider process/native conversation is an execution Attempt, not the durable responsibility.

A native harness may support a qualified model change within its conversation. A cross-provider transition uses a new admitted Attempt under the same Job and the existing OperatorContinuation PREPARE/ACK contract. Neither path may reuse an unresolved writer or pretend the provider's private context has been transferred. A model change does not transfer custody or expand the grant.

## One-command orchestrator triage

After normal source release and installation, an already-authorized local control-socket caller can read a single original root:

```sh
python3 scripts/executive_os_phase1c.py \
  --socket "$MMX_EXECUTIVE_CONTROL_SOCKET" \
  session-recovery "$ROOT_JOB_ID" --limit 30
```

Use the actual existing socket binding and original root ID. This command is not a setup/installation command. It performs no retry, cancellation, provider call, quota reset or placement. The existing kernel-peer authorization and READY gate remain unchanged; it is not a new Web/MCP permission grant.

The response includes per-worker Job/Attempt identity, canonical status, checkpoint availability, next action and reasons. A requeued worker retains its preceding Attempt, worker and quota-stop cause, with `stop_reason_scope=previous_attempt`; the view does not pretend that predecessor is still running. `count_by_action` describes the returned set. `has_more` explicitly marks bounded output. Missing scheduler evidence remains missing: queue position and ETA are null, not guesses.

| Diagnostic action | Meaning | Existing owner that acts |
| --- | --- | --- |
| `REQUEUE_WITH_EXISTING_COO` | Current non-modifying quota proof permits the existing retry path. | Existing COO cycle; it rederives evidence atomically. |
| `WAIT_FOR_EXISTING_SCHEDULER` | The same Job is durably queued; this view has not established capacity. | Existing scheduler/Capacity owner. |
| `RECONCILE_ORIGINAL_ATTEMPT` | A writer/effect or its release evidence is unresolved. | Original Attempt/generation/effect owner. |
| `ATTEMPT_ALLOWANCE_DECISION_REQUIRED` | Existing attempt allowance is exhausted. | Existing grant/budget decision owner. |
| `OWNER_DIAGNOSIS_REQUIRED` | Failure cannot be classified as an automatically safe retry. | Existing runtime/operator owner. |
| `INSPECT_TERMINAL_RESULT` | The Job is terminal; result/acceptance still need their own evidence. | Existing result/acceptance owner. |

The installed native Fabric's own `fabric_task.py status RUN_ID` remains a separate transport observation for already-running legacy workers. Do not assign invented Executive Job IDs to those workers or launch replacements merely because the high-level view cannot join them.

## Automatic routing contract

The target recovery policy uses existing Model Router suitability and Capacity placement, not a second fallback scheduler:

1. Preserve task-quality floor, required tools/skills, context fit, grant, budget and source custody.
2. Prefer the same qualified model in another already-authorized independent pool when capacity exists.
3. Otherwise select a qualified equivalent model/harness, rehydrate the same logical worker and require successor acknowledgement.
4. When all qualified slots are occupied or exhausted, leave the existing Job queued. Expose the actual reason and known reset/release condition through the existing parent-return/event path. Do not silently downgrade the task.

Model, harness, host, account and quota scope are different dimensions. A host change creates no new provider quota. A model-specific allowance and an account-wide allowance can apply simultaneously; a route is usable only when every applicable scope permits it. Fable-specific exhaustion can permit another model when the account-wide allowance remains; account-wide exhaustion cannot be solved by renaming the model. Cursor is a product/harness and does not by itself prove a model is equivalent.

Use-it-or-lose-it preferences belong inside already-qualified candidates. Reuse #1365 model/host selection, #1253 pool-family accounting and #1247/#1248 qualification/capacity. Unknown or stale quota telemetry is not available capacity. Recovery never enables unapproved API billing, weakens a denied tool policy, or rotates accounts to evade a safety/permission refusal.

For a 30-worker interruption, preserve 30 logical Jobs and at most one current admitted writer per Job. Deduplicate notifications by original Attempt/command; coordinate shared quota scope through the existing Capacity owner. One event storm must not multiply the root's concurrency/descendant grant or produce 30 retries of each worker.

## Context exhaustion

`context_plan` consumes adapter-observed context capacity and token estimates. It reserves space for the next input, model response, tool results and recovery/compaction before admitting another turn. The source tests now catch the case where ordinary output fits but would consume the final recovery headroom.

If the next input plus mandatory reserves cannot fit even in an empty context, return `REBUILD_NEXT_TURN_CONTEXT`; repeatedly compacting or rotating cannot fix that input. If native compaction is supported and can still fit, use the existing generation-bound checkpoint INTENT/APPLIED operation and remeasure before the next turn. Otherwise resume from the durable frontier through the existing continuation owner. Unknown capacity returns `OBSERVE_CONTEXT`.

The portable frontier contains the task goal and constraints, exact source revisions, accepted artifacts/tests, completed work that must not be repeated, next action, unresolved effects, child obligations and parent-return references. Keep bulk history and logs as source-owned references. Provider-private encrypted compaction items are not cross-provider portable memory. `portable_context_fit` never truncates mandatory state to squeeze into a smaller target model.

A checkpoint is not proof of safe predecessor termination or successor consumption. Abrupt quota loss may require reconstructing the current frontier from already-durable source and effect records, without another call to the exhausted model.

## Current review findings and effect fence

Independent read-only review `fabric-session-recovery-review-20261012-r1` finished and its result was consumed. Ledger readback is `ACCEPTED` for the review task, not approval of this source release. The reviewer found no bypass of the stated live-writer/unknown-effect/modifying-grant fences, but identified these correctness defects:

- Operator-authored `JOB_RATE_LIMITED` is not accepted by the current proof producer, even though it is an existing canonical producer path.
- Historical receipt replay unnecessarily rereads mutable generation state and can be invalidated by later observations.
- Hashing an entire Event row makes historical proofs brittle under an additive table column.
- The proof JSON loader differs from the Runtime's canonical JSON wire.

Five new deterministic regression tests reproduce those defects. They remain ordinary failing tests, not skipped/xfail cases. A proposed quota-proof rewrite was blocked by the tool safety check before execution. Original-target readback confirmed it did not apply; preparatory edits were rolled back to the published proof module. That refused effect was not retried through another tool, worker, account or model. The independent control-socket/context changes proceeded without altering that module.

## Acceptance still owed

Keep #1367 draft. Resolve the open review failures on a permitted surface, complete exact-head independent review and required checks, compose #1289/#656 continuation compilation with the qualified provider adapters, and qualify real same-model/different-pool and cross-provider recovery. The successor must acknowledge and consume the frontier, perform useful work, and return to the original parent. Test all-slots-busy, reset/slot-return wake, shared quotas, cold restart and 30 distinct workers under the same original capacity grant. Mock registrations and synthetic release rows are not evidence of that production journey.

## Public API evidence checked October 12, 2026

- Claude Code model configuration: https://code.claude.com/docs/en/model-config — native model switching exists; the documented fallback chain is not generic quota failover.
- Claude plan usage: https://support.claude.com/en/articles/11145838-use-claude-code-with-your-pro-or-max-plan — account-level limits are shared across Claude and Claude Code, with additional model-specific limits where applicable.
- Codex App Server: https://developers.openai.com/codex/app-server — retained thread resume can select a different model; thread compaction has an asynchronous completion event, not an immediate completion proof.
- Cursor CLI: https://cursor.com/docs/cli/reference/slash-commands — model selection, resume and conversation summarization are native surfaces.
- Cursor SDK: https://cursor.com/docs/sdk/typescript — per-run model override and stored-agent resume exist. A documented SDK capability does not prove that this organization's installed adapter implements it.

These sources establish native feasibility, not installed Fabric qualification, model equivalence, pool independence or release authority.

## October 12 continuation: tested delivery and expanded triage

The new tests go beyond retaining checkpoint columns. `tests/test_executive_session_recovery_consumption.py` uses the real generation-bound checkpoint operation, Runtime, supervisor prompt producer and successor adapter callback. After Runtime reopen, a second registered pool receives the exact frontier; the model substitute derives a result from the saved next action and the original owner records its result seal. The same logical Job, root and READ-only grant survive. The exhausted predecessor pool remains RATE_LIMITED. The three tests pass; process/provider observations are fake, so this is not real provider migration or original-parent wake acceptance.

This also exposes a default-path integration gap: the modern orchestrator stop emits `OPERATOR_OPERATION_APPLIED`, but the quota proof recognizes legacy `OHF_GRACEFUL_STOP`. The actual modern-path test safely stays held, with its checkpoint intact. The passing continuation test uses the existing typed legacy release API rather than fabricated database release rows. Do not claim the modern path is wired, manufacture a legacy receipt, or change production stop routing to sidestep missing proof integration.

### Richer first-page operator response

The unchanged private control-socket command above now returns current registered worker/provider/model/quota status, previous pool's current status, historical stop reason, remaining attempt allowance, parent/role, root status and total child count. These are observations: registration is not served-model proof or eligibility. A quota reset followed by BUSY can be distinguished from the original quota stop, without restarting the waiting Job. A real disposable socket test returns all 30 distinct fixture Job records with the richer fields; this is not 30 launched paid agents.

`project_root_recovery` additionally accepts `after_job_id` in the **pure read library**. It validates cursor membership in the same original root and returns a next cursor for keyset traversal. Every page is its own read snapshot, labeled LIVE_KEYSET; concurrent inserts before a cursor can require a fresh scan. `observed_event_id` is an observation watermark, not an immutable snapshot or authority token. Returned action counts apply only to the page; `total_jobs` is the root's observed total.

**CLI/socket pagination remains unimplemented.** Its source edit was safety-blocked before dispatch and exact readback showed no change. No alternative endpoint or retry was used. The CLI does not expose `--after-job-id`. Two ordinary failing tests preserve this integration requirement. The existing first-page limit can still return up to 500 children; never imply a cursor field in a library response is an installed transport feature.

### Numeric context dependency for the incumbent Codex adapter

`control_plane/codex_context_projection.py` is a side-effect-free adapter dependency, not a new adapter. Its intended consumer is #1340's existing `_ingest_turn_notifications` path after current thread/turn/completion/helper checks. It preserves only selected numeric usage and provenance fields. It ignores foreign identities, returns unknown for malformed/absent observations, rejects booleans/non-integers/out-of-int64 values, and uses request-local `tokenUsage.last.totalTokens` rather than cumulative `total`. Cached/reasoning components are not counted twice. `modelContextWindow` can be unknown; no auto-compaction threshold is guessed. After compaction/context mutation, the current generation must be remeasured before planning another turn.

Reference contract: official OpenAI `codex-rs/app-server-protocol/schema/json/v2/ThreadTokenUsageUpdatedNotification.json` in https://github.com/openai/codex and the App Server event reference at https://developers.openai.com/codex/app-server/. Public current schema is not installed-binary attestation. The dependency's tests use the documented shape but do not prove the native adapter emits/consumes it. No live adapter file was changed; #1340's active source remains with its incumbent.

### Updated evidence and hold

Expanded campaign: **270 tests, 263 passed, 7 failed, no errors/skips**. It includes the whole existing operator-supervisor test module plus affected quota/triage/context/client/service/consumer/telemetry tests. Seven failures are the five original quota proof cases and two unimplemented cursor-transport cases, not suppressed with skip/xfail. The modern-stop mismatch is a separately documented held behavior with a passing safety test. See `research/evidence/fabric-session-recovery-expanded-20261012.junit.xml` and the cumulative plan for exact hashes and source custody. Source-only, draft/hold, not installed or release-approved.

## Installed-schema qualification and source adapter hook

The later source increment supersedes the earlier statement that the numeric helper is unintegrated: it is now connected to the existing Codex event normalizer in this candidate branch. The installed adapter is still unchanged. Read-only comparison against #1340 head `3b231e6cc273315ac4a279f9793a9a9419de0460` found the normalizer, closed-turn endpoint and event reader methods AST-identical before our hook. The disjoint 13-line source addition follows existing helper/thread checks, validates the exact current native turn and refuses to attach context to generation-only or completed-turn events. It stores numeric usage in the existing normalized Event, not a new state store, and performs no automatic compaction or retry. #1340's own branch was not changed.

**155 adapter/telemetry tests passed**, including the complete existing Codex adapter suite and new foreign-turn/thread, closed-turn, secret-redaction and unknown-count cases. Before the hook, three new tests failed because the numeric payload was missing. Evidence: `research/evidence/fabric-context-adapter-integration-20261012.junit.xml`. These are local fake-App-Server tests, not paid-provider calls or deployment proof. The seven held quota/transport regressions remain.

The installed `codex-cli 0.159.3` also exported its actual protocol schema using an isolated credential-free home. Its native arm64 executable SHA256 is `4d210f7c5a18fd0386434df23b5bdbb8c0e7257d3e8a2b30b0769c8bbe99a878`; the usage schema digest is `aba4f6c7e4a19b2b842c08ee793b57000c07dafd57b922ad0d8e7c76609108c2`. Selected export evidence is recorded in `research/evidence/fabric-context-native-schema-20261012.json`, and the exact usage schema is retained under `tests/fixtures/codex_context/`. No login, model turn, live compaction, credential installation or production mutation was requested. **73 focused schema/telemetry/consumer checks passed** before the adapter hook; counts overlap and are not additive.

This narrows the remaining uncertainty from documented API feasibility to tested local protocol compatibility plus source-level event handling. It does not prove actual provider-event delivery, successor model equivalence, automatic compaction actuation or full production failover. Compose the source hook with the incumbent rich-worker branch and obtain normal review/release and real-path evidence before adoption.

## Registered capacity — observation, not admission (October 12 increment)

A queued logical worker now has a `registered_supply` view derived within the same existing Executive SQLite read transaction. It counts the statuses of quota registrations only inside that Job's existing `eligible_quota_classes` allowlist. It reports `registered_free_count`, `state_counts`, and a diagnostic next action:

- `WAIT_FOR_EXISTING_CAPACITY_OWNER`: no free *registered* slot was observed (e.g., BUSY and RATE_LIMITED classes). The Job stays queued; no ETA is inferred.
- `REQUEST_EXISTING_PLACEMENT_REVALIDATION`: a free registration was observed. Model Router, quota/budget, provider admission, host capacity and lease allocation are **still unproven**; no worker is dispatched by this read.
- `REQUIRE_CANONICAL_CAPACITY_SCOPE`: allowlist missing or malformed; never invent usable capacity.
- `REQUIRE_CAPACITY_STATE_RECONCILIATION`: an unexpected registry status was observed; no selection permission follows.

`route_qualified=false`, `independent_budget_proven=false`, `shared_quota_verified=false`, `telemetry_freshness_verified=false`, and `can_reserve=false` are intentional guards. `reset_eta` remains null. Counts omit account labels and authentication material. The parent-level `registered_free_slots_not_additive_across_jobs=true` prevents mistaking one free registration viewed by 30 workers for 30 independent execution slots. `recovery_queue_count` is scoped only to the returned page, not the entire root.

This is **not** an alternative to #1253's shared-budget accounting, #1365's model/host qualification or the existing atomic capacity owner. It adds no reservation, scheduler, retry or wakeup. Its currently verified source tests are not evidence of installed or live quota availability.

## Legacy native Fabric batch triage (source-only candidate)

Some existing Grok/GLM/Cursor runs are identified by the account-local native `fabric_task.py` RUN_ID, not by an Executive Job. **Do not invent Executive Jobs or deduce a native run's root/custody from its run ID alone.** Once this source is reviewed and available on the authorized host, a caller with exact original run IDs can use a one-shot, read-only summary:

```sh
python3 scripts/fabric_legacy_triage.py \
  --fabric-task "/ABSOLUTE/INSTALLED/ext/fabric_task.py" \
  --expected-sha256 "<EXACT_INSTALLED_SOURCE_SHA256>" \
  --run-id "RUN_ID_1" --run-id "RUN_ID_2" \
  --timeout-seconds 5 --total-seconds 30
```

The caller supplies the authorized absolute installed file and its verified SHA, plus 1–100 exact previously commissioned run IDs. The CLI invokes only the incumbent `status RUN_ID` action, without a shell, request, wait-loop, result acceptance, cancel, retry, or provider call. A changed installed script fails its digest check. A whole-batch deadline caps stalls; a missing/timeout/unreadable result becomes `RECONCILE_ORIGINAL_STATUS` without suppressing other workers.

State meanings are deliberately conservative: `ACTIVE_OR_WAITING` is *not* proof of running, `EFFECT_UNKNOWN` requires original-carrier reconciliation, `TERMINAL_FAILURE` does not imply exhausted tokens, and even successful `TERMINAL` requires delivered result and accepted outcome before reporting `CONSUME_ACCEPTED_RETURN`. Native `QUEUED` and cross-model retry cannot be inferred from `fabric_task.py status` and are always reported unconfirmed. Full stdout, provider session IDs, raw payloads, quota/account values, and potential secrets are not returned in the batch summary. It adds no state store or daemon.

**Verification boundary:** 29 unit/runner tests passed, including 30 mixed original run IDs, duplicate/malformed-run rejection, fake pinned status invocation, timeout isolation and total-batch deadlines. JUnit `research/evidence/fabric-native-batch-triage-20261012.junit.xml`, SHA256 `bdc09cc5b793030ddf7c80b82d128f3b24e51a09bfd617bad183b157c7c9f40d`. One isolated end-to-end subprocess test `test_actual_entrypoint_runs_from_unrelated_working_directory` was safety-blocked before dispatch and has **not** been verified; do not rerun through another carrier to bypass that denial. No installed native kit code or live worker was changed. This CLI is a source candidate and is not claimed deployed.

## Native Codex context / model-switch qualification — further October 12 source increment

Actual installed Codex App Server **0.159.3** exported:
- `ThreadResumeParams.json` SHA256 `c818e26d830ac4430791eab7d4a872d2384fa6006b14c505d8caf46e7e093527`: required `threadId`; optional `model` field.
- `TurnStartParams.json` SHA256 `2dfcf68705896fadc344ccfeb2e9fe5a6bcbbb8b9a90cf449ce232b636daf05a`: required input/thread ID; optional `model`.
- `ContextCompactedNotification.json` SHA256 `c9f9a58ef680e09d568cff5f24b45895841e1cf138b650bae64dcf6c85f177af`: required `threadId` and `turnId`.

These are **protocol capabilities**, not a successful model change or entitlement to reuse private threads across providers/accounts. Current Model Router/Capacity/RuntimeBinding must still establish qualified target, budget and exact writer release. #1344 native continuation source has merged, but this does not prove the installed service selects it or that a model swap is authorized.

The native `thread/tokenUsage/updated` wire exposes **last-request usage**, not an independently attested current-context occupancy counter. The projected `last_request_tokens` is useful observational telemetry; `context_occupancy_tokens=null` and `usable_as_context_plan_used_tokens=false` explicitly prevent passing request-local spend as reliable context fullness. Consequently the current planner responds `OBSERVE_CONTEXT` until a true occupancy source is qualified. No automatic provider compaction threshold was invented.

The adapter now projects an exact-thread/turn `thread/compacted` asynchronous notice as `context_compaction` on the **existing** generation-scoped redacted Event. A notification can demand remeasurement but is **not** the Executive checkpoint INTENT/APPLIED receipt, proof of durable memory transfer, or restart/model-switch authorization. Foreign-thread, foreign-turn, closed-turn and generation-only notifications cannot claim active turn compaction. No new event store, scheduler or compaction call.

The adapter/context/diagnostic campaign passed **218 tests, zero failures/errors/skips**: `research/evidence/fabric-context-compaction-observation-20261012.junit.xml`, SHA256 `0203c6f1fbd84e3cc0452b1fc00239ba0273cab9441d555b2d15f6c7492b35cf`. This tests fake native events and the existing adapter, not a live model turn, compaction, installation or account migration.

## Original-root native triage and stale controller evidence (October 12 follow-up)

The source-only native batch CLI now accepts `--expected-root-id ROOT_ID` and, for a single original parent group, `--expected-parent-run-id PARENT_RUN_ID`. IDs are validated before reading any native status, using the incumbent native RUN_ID grammar. Caller-supplied identity is a comparison requirement, **not** a credential, capability, root registration, or execution grant.

The incumbent `fabric_task.py status` returns `root_id`, `parent_run_id`, and `acceptance_state` only through its existing terminal/ledger projection. A successful, result-present, ledger-accepted native status without exact **caller root and parent** matches now returns `VERIFY_ORIGINAL_PARENT_BEFORE_CONSUMPTION` or `RECONCILE_ORIGINAL_IDENTITY`; it no longer recommends `CONSUME_ACCEPTED_RETURN`. A missing/mismatched root or parent on an unaccepted terminal result likewise prohibits reviewing it under the wrong root. Exact matching allows the *recommendation* to consume but always reports `return_consumed_by_parent=false`; ledger lineage is not an authenticated live-parent ACK.

For `ACTIVE_OR_WAITING`, the incumbent's `controller_observation` has distinct evidence states. Valid `STALE_NO_TERMINAL_EVIDENCE` now routes to `RECONCILE_INCUMBENT_CONTROLLER`; valid `LOCAL_POLL_EVIDENCE_ONLY` remains `OBSERVE_INCUMBENT_CONTROLLER`. Neither observation proves provider liveness, termination, rate-limit exhaustion or retry admission. The numeric silence lower bound is retained only when typed and nonnegative; raw logs, dates and unrelated provider text are not emitted. The controlling native run remains owned by its original carrier.

**Verification:** 57 native-library/CLI-unit cases passed, 0 failures/errors/skips, artifact `research/evidence/fabric-native-lineage-20261012.junit.xml`, SHA256 `e4b07b427b7a5dc4bf12496d1fb6577a0531af761eb7c75b1e3883a2857b2d23`. The previously safety-denied independent actual entrypoint-from-unrelated-CWD subprocess test remains excluded and unverified. No installed native script or remote run was modified or restarted.

## Executive SQLite WAL schema preflight — concurrency repair (October 13 UTC)

A CI 30-duplicate-callback test reported `database disk image is malformed` when multiple `Runtime.at` constructors verified the same Executive SQLite v5 database. Inspection of the preflight found that its `mode=ro&immutable=1` read bypassed SQLite WAL locks and could read stale main-file schema bytes while a newer DDL was only in WAL. This is not evidence of actual disk corruption. A controlled SQLite probe showed that immutable mode did not see an active WAL-only table, while `mode=ro` did.

The current isolated source candidate updates only `RuntimeStore._inspect_existing_writable_schema` (plus a bounded barrier failure diagnostic in the existing SQLite contention test). No migration schema, Job/Attempt/effect semantics, unknown-effect retry, quota-proof logic, queue or service authorization is changed.

- With an already-present, protected WAL/SHM pair, read the migration vector and reviewed schema digest from **one SQLite `mode=ro` transaction**, respecting native WAL locks and snapshot semantics.
- With absent or incomplete sidecars, first read the main file using `mode=ro&immutable=1` without creating sidecars. An invalid schema stays rejected. A positively verified v5 main file with changing WAL activity may then be rechecked with SQLite's WAL-aware read-only connection. An incomplete, unchanged/orphaned WAL cannot silently qualify as current.
- Allow at most **four bounded re-acquisitions of read-only schema snapshots** on observed WAL creation/removal churn. This is not a worker retry, Job replay, lock steal or effect-clearing operation. A stable invalid schema, unreadable sidecar identity or persistent churn refuses startup.
- Retain the existing exact v5 migration vector, per-migration checksums, full reviewed DDL digest, upgrade barrier and inode identity requirements. Stale offline databases cannot use a read-only schema discovery to manufacture new WAL sidecars.

**Verified source tests** on disposable databases: 12/12 WAL hardening (including 30 concurrent startups without pinned WAL sidecars, 30 concurrent startups with a pinned WAL reader, synthetic WAL-only foreign DDL, an orphan WAL, and stale checksum/DDL failures), JUnit `research/evidence/fabric-wal-preflight-hardening-20261013.junit.xml` SHA256 `ee0a1a2e50cd271418a7134b446f7463335c0ec9d68a177e90b9afb0c4f36786`; broader Runtime/SQLite/quota-rollover 189/189, JUnit `research/evidence/fabric-wal-preflight-expanded-20261013.junit.xml` SHA256 `2fbf86a018bc0e18f79c1c8bbf2f31d2b5f5ce2efa83bdbb578fa7dbb685fbc4`; backup/restore/wake 146/146, JUnit `research/evidence/fabric-wal-backup-wake-20261013.junit.xml` SHA256 `4a684c1c7c0ebf708c3d101aaf2ef5bcd5782e0622e878d978c05ac5c3d04778`. The 12 are included within the 189; do not add overlapping counts blindly.

The original existing `test_atomic_claim_allows_exactly_one_winner_across_runtime_instances` was hardened to bound its test-only synchronization wait and report both startup failures. The earlier unbounded barrier stalled during failing preflight experiments; normal owner now reports a finite failure instead of hanging CI. It does not change production dispatch.

**Acceptance distinction:** these are strong source/test results, **not** a passing GitHub CI run on the final published commit, an installed Executive Runtime, or evidence that the original CI error has been eliminated across environments. PR #1367 must remain draft/hold while the five known quota-proof RED tests, two refused socket-cursor RED tests, modern-stop receipt mismatch, independent source review and live provider failover/parent-consumption canaries remain unresolved. The previously denied quota-proof and cursor modifications were not attempted or bypassed.

## Modern-stop proof diagnostics and strict COO fan-out — October 13 continuation

The *current* operator-harness graceful-stop path records `OPERATOR_OPERATION_APPLIED`, with exact `operation_kind=graceful_stop`, `process_liveness=PROVEN_DEAD`, `provider_writer_state=RELEASED` and `executive_writer_released=true`. The unchanged positive quota-proof module still requires legacy `OHF_GRACEFUL_STOP`. This is an existing producer/consumer contract mismatch; **do not synthesize the legacy event, reinterpret the receipt as authorization to retry, or bypass the original quota-proof owner**.

The root-scoped `session-recovery` diagnostic now labels `MODERN_STOP_NOT_LEGACY_QUOTA_PROOF` only for a RATE_LIMITED Attempt whose exact supervisor-applied stop receipt, source-bound process generation and released writer exist but a matching legacy generation stop event does not. The `next_action` remains `RECONCILE_ORIGINAL_ATTEMPT`; the existing classifier alone can produce `REQUEUE_WITH_EXISTING_COO`. An absent/foreign generation or malformed receipt cannot spoof this diagnostic. It is an explanation of why a safe-appearing stop is held, **not** an alternative release proof or a modification.

An important capacity boundary was confirmed from the existing protected `coo_cycle_policy`: `max_fan_out_per_parent=8`, `max_children_total=16`, `max_depth=1`. These are strict-v2 COO *plan-admission* limits, separate from the independent native Fabric broker's lease capacity and from the Runtime bounded-read page maximum of 16. The root triage now reports the pinned policy SHA and its limits, direct child count and whether the observed count exceeds the reviewed ceiling. A 30-child *fixture* inserted directly into SQLite exceeds this policy and must not be represented as 30 legitimately admitted COO workers. This view never widens authority; it also does **not** imply native Fabric cannot maintain 30 separately admitted runs under its own existing law.

**Verification:** focused Modern Stop / COO policy / root triage / SQLite retry tests: 117 passed, 0 failed/errors/skips. `research/evidence/fabric-modern-stop-policy-expanded-20261013.junit.xml` SHA256 `89f8e636f837829bf0ad7a0b326a4662de35183550198e9233cecd1cc3f9e684`. A new adversarial test first caught an unbound forged receipt being labeled as a modern-stop gap; the final read-only diagnostic requires exact generation ownership and positive released-state observation. No source quota proof or service-cursor mutation was made.

The latest completed GitHub CI for prior head `26c96204e96b1b03d433c87c08f95feb4e5772f5` failed on precisely the **five already-known quota-proof tests and two socket cursor integration tests**; the prior sporadic SQLite malformed-database error was **not present** in that run. Other CI checks were green. This is one supporting CI observation, not an unconditional lifetime fix.

An independent fresh read-only Fabric review request using original root/parent `fabric-session-continuity-20261012-web-001` and new ID `fabric-session-recovery-wal-review-20261013-r1` was refused by the incumbent broker: no eligible host cleared current disk, load, thermal and qualification constraints. Exact original ID status is `NOT_FOUND`, so there is **no active reviewer or uncertain work to replay**, and the request was not rerouted or forced to another host. Review remains owed after actual capacity/admission changes. All source remains PR-draft and not installed.
