# MAT-C1 — Effect-certain G1/G2 materialization receipt plan

**Date:** 2026-09-02  
**Owner:** Sol, AI CEO  
**Chairman:** Chris  
**Parent architecture:** `docs/superpowers/specs/2026-09-02-autonomy-session-materialization-mat-f0-design.md`  
**Architecture operation:** `autonomy-session-materialization-mat-f0-architecture-freeze-20260902-sol-001`  
**Implementation wave:** `MAT-C1_EFFECT_CERTAIN_G1_G2_RECEIPT_AND_RECONCILIATION`  
**State:** `PLAN_ONLY / NOT_STARTED / PRODUCTION_DISARMED / HOLD-FOR-SOL`

## 1. Mission

Make the existing read-only Executive planner recover an exact Codex process/session observation when
control loses the response before either:

```text
G1 TX-3 start bind
G2 TX-11 resume bind
```

Do so without a second provider call, second Attempt, G3, or another lifecycle/current-session store.

This plan authorizes no implementation until MAT-F0 is protected.

## 2. Gate

<!-- MAT_C1_GATE_BEGIN -->
```json
{
  "schema": "mastermind.session_materialization_mat_c1_gate.v2",
  "architecture_operation": "autonomy-session-materialization-mat-f0-architecture-freeze-20260902-sol-001",
  "architecture_schema": "mastermind.session_materialization_f0_contract.v2",
  "protected_source_basis": "2c59fc6a987b02b2ca3db4e59fb90a5246eaed12",
  "records_only": true,
  "runtime_effect": false,
  "provider_effect": false,
  "production_armed": false,
  "implementation_state": "HELD_UNTIL_MAT_F0_PROTECTED_AND_CURRENT_COLLISIONS_RECONCILED",
  "first_vertical": "openai-codex / codex-app-server / plan / READ / no writes",
  "canonical_operations": {
    "G1_START": "ohf-op:start:<attempt_id>",
    "G2_RESUME": "ohf-op:recover-resume:<attempt_id>"
  },
  "provider_native_idempotency": false,
  "maximum_generation": 2,
  "stage_b": "SEPARATE_AND_HELD",
  "candidate_paths": [
    "control_plane/operator_materialization_receipt.py",
    "control_plane/executive_worker_broker.py",
    "control_plane/remote_codex_operator_adapter.py",
    "control_plane/executive_operator_supervisor.py",
    "tests/test_operator_materialization_receipt.py",
    "tests/test_executive_operator_broker.py",
    "tests/test_executive_operator_supervisor.py",
    "tests/test_ohf_p1b_runtime_orchestrator.py",
    "tests/test_autonomy_session_materialization_source_law.py"
  ],
  "protected_paths": [
    "control_plane/executive_runtime.py",
    "control_plane/operator_harness_orchestrator.py",
    "control_plane/executive_operator_harness_port.py",
    "control_plane/session_targets.py",
    "control_plane/sol_action_target.py",
    "control_plane/runtime_binding_projection.py",
    "control_plane/executive_terminal_return.py",
    "control_plane/wake_*",
    "data/control_plane/*",
    "ops production arming/configuration"
  ],
  "implementation_predecessors": [
    "MAT-F0 protected",
    "current-base collision archaeology",
    "exact current Skillpack re-pin"
  ],
  "production_canary_predecessors": [
    "accepted complete teardown lifecycle",
    "current host autonomy and identity gates green",
    "exact release and worker/provider attestation",
    "explicit bounded canary arming",
    "independent exact-release review"
  ],
  "next_after_records": "INDEPENDENT_EXACT_HEAD_REVIEW_THEN_PROTECT_MAT_F0"
}
```
<!-- MAT_C1_GATE_END -->

## 3. Routing

```text
COGNITION_ROUTE: CHAT_PRO_DEFAULT
PREFERRED_AVENUE: CTO Sol
WHY: bounded but architecture-sensitive distributed effect reconciliation across Runtime, broker,
     filesystem evidence, process identity, and provider session identity.
WHY NOT FABLE: MAT-F0 freezes the authority and product boundary; ordinary bounded specialists can
               implement and independently review it.
RECEIVER_BINDING_MODE: CAPACITY_SELECTABLE
PLACEMENT_STATE: WAITING_CAPACITY / needs_placement
```

Routine placement is not Chairman labor. Do not issue a worker-facing commission until a lawful
concrete receiver exists.

## 4. Authority precedence

1. action-time protected Skillpack and universal dialogue/routing laws;
2. protected MAT-F0 v2 contract;
3. current protected Runtime, Operator Harness, service, broker, adapter, teardown, RET1 and Stage B;
4. this plan;
5. PR/Slack/worker prose as evidence only.

Any candidate-path collision or owner change returns to Sol before write.

## 5. State before

- exact planner dispatch, start/resume INTENT, provider-dispatch commitment, TX-3/TX-11/TX-4, and
  G1→G2 recovery exist behind default-off gates;
- worker `ohf-start` and `ohf-resume` share `_ohf_start(..., resume=<bool>)`;
- worker active operator state is process-local;
- no immutable provider observation survives a lost worker response;
- `reconcile_restart()` requires already-bound identity and accepts only exact current G1 today;
- provider-native idempotency is false and current OHF permits no G3;
- complete wait/monitor/pipe teardown remains a production-canary predecessor.

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
control_plane/executive_operator_supervisor.py
tests/test_executive_operator_broker.py
tests/test_executive_operator_supervisor.py
tests/test_ohf_p1b_runtime_orchestrator.py  # only if the exact loss seam needs it
tests/test_autonomy_session_materialization_source_law.py
```

The source-law test is a required transition path. Preserve its architecture/no-rebuild assertions
while replacing `NOT_BUILT` characterizations with exact G1/G2 implementation proof.

### Protected absent a new Sol ruling

```text
control_plane/executive_runtime.py
control_plane/operator_harness_orchestrator.py
control_plane/executive_operator_harness_port.py
control_plane/session_targets.py
control_plane/sol_action_target.py
control_plane/runtime_binding_projection.py
control_plane/executive_terminal_return.py
control_plane/wake_*
data/control_plane/*
ops production arming/configuration
```

## 7. Non-goals

No general session factory; no other role/provider; no ChatGPT-Web creation; no Stage-B assignment;
no Wake/ACK; no Capacity/router change; no write-capable session; no new table, lifecycle, lease,
queue, scheduler, registry, daemon, retry plane, automatic requeue, account failover, G3, production
arming, or “autonomy complete” claim.

## 8. Ordered implementation

### Task 0 — Re-pin and collide

1. Load current protected Skillpack and protected MAT-F0 v2.
2. Inspect every open PR touching candidate paths.
3. Confirm teardown source/path relation and keep canary held until complete.
4. Freeze exact implementation paths.
5. Return to Sol on overlap or owner contradiction.

### Task 1 — Pure receipt contract

Create `operator_materialization_receipt.py` as stdlib-only, deterministic, and I/O-free except pure
byte helpers. It owns:

- exact v1 schema/key set;
- strict canonical JSON with duplicate-key refusal;
- receipt digest;
- SHA-256 operation-command path derivation;
- bounded size;
- exact semantic equality/conflict;
- typed nested wire validation for start/resume observations and principal evidence.

It imports no Runtime/provider/service module and grants no currentness or authority.

Required negatives: missing/unknown key, duplicate key, noncanonical bytes, oversized content,
malformed command/Attempt/epoch/generation, invalid start-vs-resume generation, changed profile,
provider-session mismatch, malformed process/principal/home evidence, digest drift, secret/private
fields, and caller-path influence.

### Task 2 — Symmetric worker durability

Extend existing `ExecutiveWorkerBroker._ohf_start(payload, resume=<bool>)` for both routes:

```text
ohf-start  → operation_kind=start_session  → G1
ohf-resume → operation_kind=resume_session → G2
```

Hold the existing state lock across precheck, provider effect, validation, receipt durability, and
process-local publication.

Before provider I/O:

- derive exact path from operation command;
- validate expected generation (`1` start, `2` resume);
- for resume, require the exact bound provider session claim;
- exact live receipt replay returns the same receipt with zero provider call;
- receipt-only after restart directs caller to status, not modifying replay;
- semantic mismatch conflicts.

After provider effect:

1. validate provider session and process;
2. collect attestation, credentials, provider-home identity;
3. build receipt;
4. exclusive-create 0700 parents / 0600 file with symlink/link/owner checks;
5. write canonical bytes and fsync file/new parents;
6. reopen and validate;
7. publish process-local state;
8. return receipt.

Persistence failure after provider effect gets at most one same-process cleanup attempt and remains
`EFFECT_UNKNOWN`. It never invokes provider again.

### Task 3 — Exact read-only status

Add `ohf-materialization-status` with exact request identity:

```text
operation_command_id
operation_kind
attempt_id
worker_id
session_epoch_id
process_generation_id
generation_number
requested_profile_digest
expected_provider_session_id | null
```

Return `ABSENT`, `RECEIPT_CURRENT_IN_LIVE_BROKER`, `RECEIPT_ONLY_AFTER_RESTART`, or `CONFLICT`, with
the receipt only in receipt states. No provider or Runtime mutation.

### Task 4 — Remote typed status proxy

Add one exact status-read method to `RemoteCodexOperatorAdapter`. Preserve bounded timeout, one AF_UNIX
request, fixed secret-safe errors, no retry/cache/authority, and strict receipt validation.

### Task 5 — G1 import

Before current `_recovery_session()`:

1. take over only the same expired Attempt/fence;
2. find exact G1 start INTENT + dispatch commitment and prove TX-3 absent;
3. read exact G1 status;
4. missing receipt → quarantine;
5. validate receipt against Attempt/worker/profile/epoch/G1;
6. call existing TX-3 bind with historical `SessionStartObservation`;
7. call existing TX-4 seal with exact attestation/principal;
8. reconcile liveness/current ownership;
9. continue live G1, or after dead/released proof allocate existing G2.

Zero second `thread/start`.

### Task 6 — G2 import

Detect the exact current unbound G2 before the current G1-only recovery reconstruction:

1. require one already-bound, exact, released G1 in the same epoch;
2. find `ohf-op:recover-resume:<attempt_id>` INTENT + dispatch and prove TX-11 absent;
3. read exact G2 status;
4. missing receipt → quarantine;
5. require receipt `provider_session_id` equals G1’s bound session;
6. validate Attempt/worker/profile/epoch/G2;
7. call existing TX-11 bind;
8. call existing TX-4 seal;
9. reconstruct/recover current G2 directly;
10. continue only if exact broker ownership/liveness is safe; otherwise stop, terminalize, or quarantine.

Never call resume again and never allocate G3.

### Task 7 — Recovery reconstruction

Generalize the supervisor’s read-only recovery composition only as needed to recognize one exact
admitted current G1 **or G2**, validating the corresponding TX-3 or TX-11 command lineage. Do not
change Runtime or the orchestrator. If protected APIs cannot support exact import, return to Sol.

### Task 8 — Complete teardown truth

Join the accepted teardown owner. Before successful completion require process dead, provider writer
released, resource stopped/sealed, wait and monitor terminal or cancelled-and-joined, stdout/stderr
pumps terminal with descriptors closed, capture completeness truthful, and UID sweep passing.

Pending ownership → `CLEANUP_INCOMPLETE`; no `complete_attempt()`.

### Task 9 — Loss injection

Inject failure after:

1. Runtime start dispatch;
2. provider G1 start;
3. G1 receipt fsync;
4. G1 broker response;
5. TX-3;
6. Runtime G2 dispatch;
7. provider G2 resume;
8. G2 receipt fsync;
9. G2 broker response;
10. TX-11;
11. TX-4.

Every case pins provider call counts, Runtime receipts, and next lawful action.

### Task 10 — Transition source law and return

Update the protected source-law test to prove both operation routes, receipt/status owners, TX-3 and
TX-11 import, G2 provider-session preservation, no G3, missing-receipt quarantine, and no-rebuild
boundaries. Do not delete the old architecture assertions.

Return base/head, changed paths, exact tests/security checks, receipt digests, start/resume call counts,
zero second Attempt, zero G3, teardown evidence, and remaining canary gates. Keep Draft/Hold.

## 9. Acceptance matrix

| Scenario | Required result |
|---|---|
| G1 happy | one start receipt, one TX-3, one `thread/start` |
| Lost G1 response after receipt | import same G1; zero second start |
| Broker restart after G1 receipt | import G1; reconcile; optional lawful G2 after dead/released |
| Missing G1 receipt after dispatch | quarantine; zero start retry |
| G2 happy | one resume receipt, one TX-11, same provider session |
| Lost G2 response after receipt | import same G2; zero second resume/start |
| Broker restart after G2 receipt | import/reconcile/terminalize G2; no G3 |
| Missing G2 receipt after dispatch | quarantine; zero resume retry |
| Changed command/profile/Attempt/generation/session | conflict |
| Concurrent exact calls | at most one provider call and one receipt per operation |
| Stale lease/fence | refusal before import |
| Symlink/link/owner/mode/digest/partial receipt attack | refusal |
| Process dead, task/pipe pending | cleanup incomplete; no completion |
| Partial capture | remains incomplete |
| Stage B absent | no target assignment invented |

## 10. Production canary

One disposable read-only planner:

1. one Job/Attempt;
2. G1 provider call once; lose response after receipt; import same G1;
3. prove G1 dead/released;
4. G2 resume once; lose response after receipt while broker remains live; import same G2;
5. one harmless turn and typed result;
6. complete teardown;
7. zero second start, zero second resume, zero G3, zero second Attempt;
8. RET1 sees terminal candidate;
9. canary configuration returns disarmed.

Separately restart the broker after a durable G2 receipt and prove deterministic import plus
terminal/quarantine behavior without G3.

## 11. Stop condition

Stop after exact-head implementation, hosted checks, and independent review. Return to Sol. Do not
merge, arm production, run the canary, start Stage B, or generalize providers/roles.

## 12. Continuation handoff

Return:

```text
operation / PR / protected MAT-F0 SHA
implementation base/head and exact paths
G1 and G2 receipt identities/digests
normal/lost/restart start+resume call counts
TX-3/TX-11/TX-4 receipts
missing-receipt behavior
zero second Attempt / zero G3
teardown proof
hosted checks and independent verdict
what merge would and would not make true
exact canary gate
```
