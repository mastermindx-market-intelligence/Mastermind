# MAT-C1 v3 — Reconciled G1/G2 materialization implementation plan

**Date:** 2026-09-03  
**Owner:** Sol, AI CEO  
**Chairman:** Chris  
**Parent architecture:** `docs/superpowers/specs/2026-09-02-autonomy-session-materialization-mat-f0-design.md`  
**Architecture operation:** `autonomy-session-materialization-mat-f0-architecture-freeze-20260902-sol-001`  
**Repair operation:** `autonomy-session-materialization-mat-f0-effect-resolution-repair-20260903-sol-001`  
**Protected source basis:** `Mastermind@caa47c1e66fe36dc3521299c918f4b9e7b2a47ca`  
**State:** `PLAN_ONLY / NOT_STARTED / PRODUCTION_DISARMED / HOLD-FOR-SOL`

## 1. Mission

Make the existing read-only Executive planner recover one exact Codex process/thread after the provider effect occurred but the control-side response or bind was lost, without another provider call, another Attempt, G3, or another lifecycle/current-session store.

The implementation preserves immutable uncertainty history:

```text
INTENT → EFFECT_UNKNOWN → RECONCILED(resolution=APPLIED)
```

It never forces `APPLIED` after `EFFECT_UNKNOWN`.

## 2. Gate

<!-- MAT_C1_GATE_BEGIN -->
```json
{"architecture_operation":"autonomy-session-materialization-mat-f0-architecture-freeze-20260902-sol-001","architecture_schema":"mastermind.session_materialization_f0_contract.v3","candidate_paths":["control_plane/operator_materialization_receipt.py","control_plane/executive_worker_broker.py","control_plane/remote_codex_operator_adapter.py","control_plane/executive_runtime.py","control_plane/executive_operator_harness_port.py","control_plane/executive_operator_supervisor.py","tests/test_operator_materialization_receipt.py","tests/test_executive_operator_broker.py","tests/test_executive_operator_supervisor.py","tests/test_ohf_p1b_runtime.py","tests/test_ohf_p1b_runtime_orchestrator.py","tests/test_runtime_binding_projection.py","tests/test_autonomy_session_materialization_source_law.py"],"canonical_operations":{"G1_START":"ohf-op:start:<attempt_id>","G2_RESUME":"ohf-op:recover-resume:<attempt_id>"},"first_vertical":"openai-codex / codex-app-server / plan / READ / no writes","implementation_predecessors":["MAT-F0 v3 protected","current-base collision archaeology","exact current Skillpack re-pin","same-carrier MAT-C1 receiver fresh pickup/START"],"implementation_state":"HELD_UNTIL_MAT_F0_V3_PROTECTED_AND_CURRENT_COLLISIONS_RECONCILED","maximum_generation":2,"next_after_records":"INDEPENDENT_EXACT_HEAD_REVIEW_THEN_PROTECT_MAT_F0_V3","production_armed":false,"production_canary_predecessors":["accepted complete teardown lifecycle","current host autonomy and identity gates green","exact release and worker/provider attestation","explicit bounded canary arming","independent exact-release review"],"protected_paths":["control_plane/operator_harness_contract.py","control_plane/operator_harness_orchestrator.py","control_plane/session_targets.py","control_plane/sol_action_target.py","control_plane/runtime_binding_projection.py","control_plane/executive_terminal_return.py","control_plane/wake_*","data/control_plane/*","ops production arming/configuration"],"protected_source_basis":"caa47c1e66fe36dc3521299c918f4b9e7b2a47ca","provider_effect":false,"provider_native_idempotency":false,"records_only":true,"repair_operation":"autonomy-session-materialization-mat-f0-effect-resolution-repair-20260903-sol-001","resolution_receipts":{"normal":["INTENT","APPLIED"],"recovered":["INTENT","EFFECT_UNKNOWN","RECONCILED"]},"runtime_effect":false,"runtime_reconciliation_methods":["OperatorHarnessRegistry.reconcile_start_result","OperatorHarnessRegistry.reconcile_resume_result"],"schema":"mastermind.session_materialization_mat_c1_gate.v3","stage_b":"SEPARATE_AND_HELD","work_admission_schemas":["mastermind.orchestration_work_admission/v1","mastermind.orchestration_work_admission/v2"]}
```
<!-- MAT_C1_GATE_END -->

This plan authorizes no implementation until MAT-F0 v3 is protected.

## 3. Routing

```text
COGNITION_ROUTE: CHAT_PRO_DEFAULT
PREFERRED_AVENUE: CTO Sol
WHY: bounded but architecture-sensitive crash consistency across existing Runtime, OHF, broker,
     filesystem evidence, process identity and provider-session identity.
WHY NOT FABLE: MAT-F0 freezes the authority and product boundary; a bounded specialist can implement
               it and an independent specialist can review it.
RECEIVER_BINDING_MODE: CAPACITY_SELECTABLE
```

The already-assigned MAT-C1 child remains PRE_START/HOLD until the architecture predecessor protects. Routine placement is not Chairman labor.

## 4. Authority precedence

1. action-time protected Skillpack and dialogue/routing laws;
2. protected MAT-F0 v3;
3. current protected Runtime, Operator Harness, service, broker, adapter, teardown, RET1 and Stage B;
4. this plan;
5. PR, Slack and worker prose as evidence only.

Any new path collision or owner contradiction returns to Sol before write.

## 5. State before

Current protected source already has exact planner dispatch, TX-2/TX-10 INTENTs, provider-dispatch commitment, ordinary TX-3/TX-11 binding, TX-4 admission, `OperationReceiptKind.RECONCILED`, the `:reconciled` command suffix, immutable Events, G1→G2 same-session recovery capped at two generations, RuntimeBinding source validation, and worker `ohf-start`/`ohf-resume` over the existing broker and Codex adapter.

It does not have a durable worker materialization receipt, read-only materialization status, Runtime `reconcile_start_result`/`reconcile_resume_result`, exact normal/reconciled terminal election, work-admission v2, or current-binding validation of the reconciled lineage.

## 6. Exact scope

### Create

```text
control_plane/operator_materialization_receipt.py
tests/test_operator_materialization_receipt.py
```

### Modify

```text
control_plane/executive_worker_broker.py
control_plane/remote_codex_operator_adapter.py
control_plane/executive_runtime.py
control_plane/executive_operator_harness_port.py
control_plane/executive_operator_supervisor.py
tests/test_executive_operator_broker.py
tests/test_executive_operator_supervisor.py
tests/test_ohf_p1b_runtime.py
tests/test_ohf_p1b_runtime_orchestrator.py
tests/test_runtime_binding_projection.py
tests/test_autonomy_session_materialization_source_law.py
```

### Protected absent a new Sol ruling

```text
control_plane/operator_harness_contract.py
control_plane/operator_harness_orchestrator.py
control_plane/session_targets.py
control_plane/sol_action_target.py
control_plane/runtime_binding_projection.py
control_plane/executive_terminal_return.py
control_plane/wake_*
data/control_plane/*
ops production arming/configuration
```

The orchestrator is protected because recording `EFFECT_UNKNOWN` after a lost response is correct. Runtime and port are in scope because v2’s claim that ordinary TX-3/TX-11 could run after uncertainty was false.

## 7. Non-goals

No general session factory; no other role/provider; no ChatGPT-Web creation; no Stage-B assignment; no Wake/ACK; no Capacity/router change; no write-capable session; no new table, migration, lifecycle, lease, queue, scheduler, registry, daemon, retry plane, automatic requeue, account failover, G3, production arming, or “autonomy complete” claim.

## 8. Ordered implementation

### Task 0 — Re-pin and collide

Load current protected procedure and MAT-F0 v3 from the same SHA; inspect all candidate-path PRs; confirm teardown ownership; freeze exact paths; return to Sol on overlap, owner change, or effect uncertainty.

### Task 1 — Pure receipt contract

Create `operator_materialization_receipt.py` as deterministic stdlib-only code owning exact receipt/status schemas, strict canonical JSON, duplicate-key refusal, digest calculation excluding `receipt_digest`, bounded size, operation-path derivation, semantic equality/conflict, typed nested observation validation, and credential-shaped-field refusal. It owns no I/O, currentness, Runtime, provider, retry, or authority.

Required negatives: missing/unknown key, duplicate key, noncanonical bytes, oversized content, malformed command/Attempt/epoch/generation, invalid start-vs-resume generation, changed profile, provider-session mismatch, malformed process/principal/home evidence, digest drift, and caller-path influence.

### Task 2 — Symmetric worker durability

Extend only existing `ExecutiveWorkerBroker._ohf_start(payload, resume=<bool>)`.

Before provider I/O, derive the exact receipt path; validate G1/G2 identity; require the exact resume session; return an exact live receipt with zero provider call; refuse receipt-only modifying replay after restart; conflict on semantic drift.

After the provider effect, validate session/process, collect attestation/credentials/provider-home identity, build the typed receipt, exclusive-create owner-only no-follow storage, fsync file/new parents, reopen/validate, publish process-local broker state, and return. Persistence failure after provider effect gets at most one same-process cleanup attempt and remains `EFFECT_UNKNOWN`; never invoke the provider again.

### Task 3 — Exact read-only worker status

Add `ohf-materialization-status` with exact operation, Attempt, Worker, epoch, generation, profile digest and expected provider session. Return exactly `ABSENT`, `RECEIPT_CURRENT_IN_LIVE_BROKER`, `RECEIPT_ONLY_AFTER_RESTART`, or `CONFLICT`. Receipt states include the exact receipt. No provider or Runtime mutation.

### Task 4 — Remote typed status proxy

Add one bounded read-only status method to `RemoteCodexOperatorAdapter`: one AF_UNIX request, fixed secret-safe errors, strict receipt validation, no retry/cache/authority.

### Task 5 — Runtime terminal-election helper

In `OperatorHarnessRegistry`, add one internal validator accepting only:

```text
INTENT + APPLIED
```

or:

```text
INTENT + EFFECT_UNKNOWN + RECONCILED(resolution=APPLIED)
```

Validate command derivation, Event columns, payload schemas, operation/generation identity, receipt digest and ordering. Mixed, missing, duplicate or drifted combinations fail closed. Normal APPLIED behavior remains byte-compatible.

### Task 6 — Runtime G1 reconciliation transaction

Add `OperatorHarnessRegistry.reconcile_start_result`. On one `BEGIN IMMEDIATE`, validate lease/fence/current G1, original INTENT/dispatch, exact `EFFECT_UNKNOWN`, absent `APPLIED`, typed worker receipt and profile digest; bind epoch session and G1 process identity; set the existing Attempt RUNNING; append one `OPERATOR_OPERATION_RECONCILED`; append no `APPLIED`; return G1. Matching replay is a no-op; changed replay conflicts.

### Task 7 — Runtime G2 reconciliation transaction

Add `OperatorHarnessRegistry.reconcile_resume_result`. Also require exact bound G1, TX-10 lineage, generation 2, and receipt session equal to G1’s immutable session. Write only G2 process identity and one `RECONCILED`. Never mutate epoch session, allocate G3, or invoke provider.

### Task 8 — Port delegation

Add exact leased wrappers `reconcile_operator_start_result` and `reconcile_operator_resume_result`. They accept typed receipt facts/digest and delegate to Runtime; no I/O or provider work.

### Task 9 — TX-4 work-admission compatibility

Factor terminal election into TX-4. Normal APPLIED writes unchanged `mastermind.orchestration_work_admission/v1`. Reconciled materialization writes exact `mastermind.orchestration_work_admission/v2`, replacing `tx3_applied_command_id` with terminal receipt kind, command id and payload digest. Exact schema-discriminated key sets only. Active-generation and G1-recovery validators consume the same helper.

### Task 10 — Supervisor G1 import

Take over only the same expired Attempt/fence; find exact start INTENT/dispatch/unresolved uncertainty; query exact status; quarantine missing receipt; validate the receipt; call the new port reconciliation method, not ordinary TX-3; call TX-4; reconcile liveness/current ownership; continue G1 or later use existing G2 only after dead/released proof. Zero second `thread/start`.

### Task 11 — Supervisor G2 import

Require exact G1/TX-10 lineage; find exact resume INTENT/dispatch/unresolved uncertainty; query G2 status; quarantine missing receipt; require the same G1 session; call new G2 reconciliation, not ordinary TX-11; call TX-4; recover current G2 directly; continue, stop, terminalize, or quarantine. Zero second resume/start and zero G3.

### Task 12 — Current binding and G1→G2 validators

Update only Runtime-owned readers to accept exact v1+APPLIED or exact v2+EFFECT_UNKNOWN+RECONCILED. `Runtime.current_harness_binding_source` rejects unresolved uncertainty, mixed receipts, stale/non-current rows, digest drift, and schema drift. `runtime_binding_projection.py` remains unchanged.

### Task 13 — Complete teardown truth

Before completion require process dead, provider and Executive writers released through existing owners, wait/monitor tasks terminal or cancelled-and-joined, pumps terminal with descriptors closed, required resource receipt sealed, truthful capture completeness, and passing dedicated-UID sweep. Pending ownership is `CLEANUP_INCOMPLETE`; no `complete_attempt()`.

### Task 14 — Loss injection and mutation proof

Inject loss after Runtime dispatch, provider G1/G2 effect, receipt fsync, broker response, `EFFECT_UNKNOWN`, `RECONCILED`, and TX-4. Pin provider call counts, receipt sets, Runtime rows, and next lawful action.

Mutations must kill replacing `RECONCILED` with `APPLIED`, deleting/ignoring uncertainty, accepting `RECONCILED` without uncertainty, mixing terminal receipts, identity/digest drift, G3, second Attempt/start/resume, overwrite, retry/failover, weakened admission schemas, or RuntimeBinding projection from unresolved uncertainty.

### Task 15 — Transition source law and return

Update the existing source-law test from architecture/gap proof to exact implementation proof without deleting architecture/no-rebuild assertions. Return operation/PR/protected architecture SHA, implementation base/head/paths, G1/G2 receipt identities, normal/lost/restart call counts, receipt/admission evidence, missing-receipt behavior, zero second Attempt/G3, teardown proof, hosted checks, independent verdict, merge truth, and the exact canary gate. Keep Draft/HOLD.

## 9. Acceptance matrix

| Scenario | Required result |
|---|---|
| G1 normal | `INTENT+APPLIED`, v1 admission, one start |
| G1 lost response with receipt | `INTENT+EFFECT_UNKNOWN+RECONCILED`, v2 admission, zero second start |
| G1 missing receipt | unresolved/quarantine, zero retry |
| G2 normal | `INTENT+APPLIED`, v1 admission, one resume, same session |
| G2 lost response with receipt | `INTENT+EFFECT_UNKNOWN+RECONCILED`, v2 admission, zero second resume/start |
| G2 missing receipt | unresolved/quarantine, zero retry |
| `RECONCILED` without uncertainty | conflict |
| `APPLIED` mixed with uncertainty/reconciliation | conflict |
| changed operation identity | conflict |
| concurrent exact calls | at most one provider call, receipt and reconciliation Event |
| stale lease/fence | refusal before Runtime mutation |
| receipt filesystem attack | refusal |
| process dead, task/pipe pending | cleanup incomplete; no completion |
| Stage B absent | no target assignment invented |

## 10. Production canary

A separate later operation proves one disposable read-only planner: one Job/Attempt; one G1 start with lost-response import; dead/released G1; one same-session G2 resume with lost-response import; one harmless turn/result; complete teardown; zero second start/resume, G3, or second Attempt; RET1 terminal candidate; configuration returned disarmed.

MAT-C1 implementation does not run or authorize this canary.

## 11. Stop condition

Stop after exact-head implementation, hosted checks, independent review, and `RESULT / HOLD-FOR-SOL`. Do not merge, arm production, run the canary, start Stage B, or generalize providers/roles.
