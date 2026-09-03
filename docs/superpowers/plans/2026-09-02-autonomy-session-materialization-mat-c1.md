# MAT-C1 — Effect-certain unbound session receipt and reconciliation plan

**Date:** 2026-09-02  
**Owner:** Sol, AI CEO  
**Chairman:** Chris  
**Parent architecture:** `docs/superpowers/specs/2026-09-02-autonomy-session-materialization-mat-f0-design.md`  
**Architecture operation:** `autonomy-session-materialization-mat-f0-architecture-freeze-20260902-sol-001`  
**Implementation wave:** `MAT-C1_EFFECT_CERTAIN_UNBOUND_RECEIPT_AND_RECONCILIATION`  
**State:** `PLAN_ONLY / NOT_STARTED / PRODUCTION_DISARMED / HOLD-FOR-SOL`

## 1. Mission

Make one existing read-only Executive planner materialization recoverable when Codex App Server
process/thread creation succeeds but the control-side response or Runtime bind is lost—without a
second provider start, a second Attempt, or another lifecycle plane.

This plan is not authority to start implementation before the MAT-F0 architecture is protected.

## 2. Gate

<!-- MAT_C1_GATE_BEGIN -->
```json
{
  "schema": "mastermind.session_materialization_mat_c1_gate.v1",
  "architecture_operation": "autonomy-session-materialization-mat-f0-architecture-freeze-20260902-sol-001",
  "architecture_schema": "mastermind.session_materialization_f0_contract.v1",
  "protected_source_basis": "2c59fc6a987b02b2ca3db4e59fb90a5246eaed12",
  "records_only": true,
  "runtime_effect": false,
  "provider_effect": false,
  "production_armed": false,
  "implementation_state": "HELD_UNTIL_MAT_F0_PROTECTED_AND_CURRENT_COLLISIONS_RECONCILED",
  "first_vertical": "openai-codex / codex-app-server / plan / READ / no writes",
  "canonical_start_command": "ohf-op:start:<attempt_id>",
  "provider_native_idempotency": false,
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
WHY: the implementation is bounded but crosses a difficult distributed effect-certainty seam among
     Executive Runtime, a distinct-UID broker, filesystem evidence and provider process/thread state.
WHY NOT FABLE: MAT-F0 freezes the product and authority architecture; no unresolved cross-repository
               strategy or principal continuity is required.
RECEIVER_BINDING_MODE: CAPACITY_SELECTABLE
PLACEMENT_STATE: WAITING_CAPACITY / needs_placement
```

Routine placement is not Chairman labor. Do not emit a worker-facing commission until a lawful
concrete receiver exists.

## 4. Authority precedence

1. action-time protected Skillpack and universal source laws;
2. protected MAT-F0 contract;
3. current protected Executive Runtime, Operator Harness, service, worker broker and provider adapter;
4. current accepted teardown source law;
5. this plan;
6. PR, Slack and worker prose as evidence only.

Any newer collision in an owner path requires finite reconciliation before first write.

## 5. State before

- The existing service can dispatch a planner and call Codex App Server through the distinct-UID
  worker broker.
- Runtime commits start intent/provider dispatch before provider I/O.
- The provider adapter creates and validates a root provider thread.
- Runtime can bind exact returned identity and can recover an already-bound G1/G2 path.
- The worker’s active operator state is process-local.
- No immutable start receipt survives a lost worker response or broker restart.
- Provider-native start idempotency is false.
- Process-group absence is not yet sufficient teardown proof.

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
tests/test_ohf_p1b_runtime_orchestrator.py  # only for a real loss-boundary discriminator
tests/test_autonomy_session_materialization_source_law.py
```

The source-law test is a required transition path: replace the protected “status operation absent”
characterization with exact receipt/status/import implementation assertions. Do not skip or delete
the architecture invariants.

### Protected unless Sol re-rules

```text
control_plane/executive_runtime.py
control_plane/session_targets.py
control_plane/sol_action_target.py
control_plane/runtime_binding_projection.py
control_plane/executive_terminal_return.py
control_plane/wake_*
data/control_plane/*
ops production arming/configuration
```

Do not add a fourth production module merely to avoid understanding an existing owner.

## 7. Non-goals

- no general session factory;
- no ChatGPT-Web materialization;
- no Claude/Grok/provider-neutral implementation;
- no non-plan role;
- no write-capable provider session;
- no Stage-B target assignment;
- no Wake/ACK implementation;
- no capacity selection/router changes;
- no new database/table/migration/queue/lease/scheduler/registry;
- no automatic requeue, second Attempt, account failover or provider retry;
- no production arming;
- no user-facing “autonomy complete” claim.

## 8. Ordered implementation

### Task 0 — Re-pin and reconcile

1. Fetch protected `master`; load same-SHA Skillpack.
2. Verify MAT-F0 protected schema and exact merge SHA.
3. Inspect all open PRs touching candidate paths.
4. Verify the teardown owner and current status.
5. Freeze the exact path ceiling on the implementation PR.
6. If an overlapping writer exists, return to Sol; do not create a duplicate carrier.

### Task 1 — Pure receipt contract

Create `control_plane/operator_materialization_receipt.py` as an import-time-stdlib-only module.

It owns:

- schema constant;
- exact key set and nested typed-wire validation;
- canonical JSON bytes and digest;
- operation-command hashing and fixed relative path derivation;
- bounded-size validation;
- replay semantic equality;
- no I/O except optional pure byte decoding helpers.

It owns no Runtime import, no provider call, no current-state query and no filesystem mutation.

Required negative tests:

- unknown/missing key;
- duplicate JSON key;
- non-canonical bytes;
- oversized receipt;
- malformed operation/Attempt/epoch/generation identity;
- inconsistent generation number;
- malformed process/attestation/principal values;
- digest mismatch;
- forbidden credential/prompt/transcript fields;
- path derivation ignores caller paths.

### Task 2 — Worker-side atomic persistence

Extend `ExecutiveWorkerBroker._ohf_start()` without changing its provider selection authority.

Before provider I/O:

- derive the exact receipt path from `operation.command_id`;
- inspect existing receipt under the state lock;
- exact receipt + exact live generation → return same receipt, zero provider call;
- exact receipt without live generation → refuse modifying replay and direct caller to status;
- semantic conflict → refuse;
- absent receipt → continue.

After successful provider start/validation:

1. build the typed receipt from exact observed values;
2. exclusive-create worker-owned directories/file;
3. write canonical bytes;
4. `fsync` file and every newly material parent;
5. re-open and validate bytes;
6. only then expose `_operator_run` and return success.

If receipt persistence fails after provider effect, perform at most one bounded same-generation cleanup
attempt, preserve effect uncertainty, and never issue another start.

Do not make file mtime, directory order or “latest” semantics authoritative.

### Task 3 — Read-only materialization status

Add one broker operation with an exact closed request schema:

```text
operation_command_id
attempt_id
worker_id
session_epoch_id
process_generation_id
generation_number
requested_profile_digest
```

Return exactly one of:

```text
ABSENT
RECEIPT_CURRENT_IN_LIVE_BROKER
RECEIPT_ONLY_AFTER_RESTART
CONFLICT
```

The response includes the typed receipt only for the two receipt states. It performs no provider or
Runtime mutation.

### Task 4 — Remote typed proxy

Extend `RemoteCodexOperatorAdapter` with a status-read method. Preserve:

- one request per AF_UNIX connection;
- bounded timeouts;
- fixed typed errors;
- no retry;
- no cache that becomes authority;
- exact receipt validation on return.

An ambiguous status read remains unknown. It never authorizes provider start.

### Task 5 — Control-side import and bind

Extend `ExecutiveOperatorSupervisor.reconcile_restart()` for the exact pre-bind start shape.

Required order:

1. take over only the existing expired same Attempt/fence under current Runtime law;
2. identify exact start operation and dispatch commitment from Runtime;
3. prove no Runtime bind/APPLIED exists;
4. query worker status using the same operation/generation;
5. validate receipt against Attempt, worker, profile digest, epoch, generation and Runtime command;
6. call the existing Runtime bind path with the receipt’s `SessionStartObservation`;
7. seal existing attestation/principal evidence;
8. re-enter the existing `_recovery_session()` path;
9. reconcile exact process:
   - live/current broker → continue;
   - dead/released → existing G2 resume of same provider session;
   - ambiguous → quarantine;
10. never create another G1, Attempt or root provider thread.

Receipt import is not a new Runtime transaction type unless current code proves the existing bind
cannot safely accept identical historical evidence. Return to Sol before adding Runtime mutation
surface.

### Task 6 — Complete teardown truth

Join the accepted teardown owner rather than weakening it.

Before successful Attempt completion, prove:

- exact process dead;
- provider writer released;
- resource stopped and sealed when present;
- wait task terminal or cancelled-and-joined;
- monitor terminal or cancelled-and-joined;
- stdout/stderr pumps terminal and descriptors closed;
- capture completeness recorded;
- UID sweep passing.

Any unresolved task produces `CLEANUP_INCOMPLETE`; do not call `complete_attempt()`.

### Task 7 — Loss-injection integration tests

Build a real in-process control↔broker test seam that can fail after these points:

1. Runtime dispatch commit;
2. provider `thread/start`;
3. worker receipt fsync;
4. broker response write;
5. control Runtime bind;
6. attestation/principal seal.

Each injection must prove the expected status and provider call count.

### Task 8 — Transition source law, hosted proof and independent review

Update `tests/test_autonomy_session_materialization_source_law.py` in this same carrier:

- preserve every architecture/no-rebuild/effect-unknown/teardown invariant;
- replace the current `materialization-status` absence characterization with exact implementation
  owner, schema, status-state, receipt-path and replay discriminators;
- ensure a mutation that re-enables second provider start dies.

Return:

```text
base SHA
exact head SHA
changed-file census
test/CodeQL results
provider start call counts for every injected failure
receipt digests
proof of zero second Attempt
proof of zero second thread/start
teardown task/resource receipts
remaining production gates
```

Keep Draft/Hold. Do not mark Ready or merge.

## 9. Discriminating acceptance matrix

| Scenario | Required result |
|---|---|
| Happy path | one receipt, one bind, one thread/start |
| Lost broker response after receipt | status read returns same receipt; zero second start |
| Lost bind response | Runtime command reconciliation; zero second start |
| Broker restart after receipt | receipt-only state; bind/reconcile G1; same thread resumed as G2 |
| Broker restart before receipt | identity unknown; quarantine; zero second start |
| Same key, changed profile | conflict |
| Two concurrent starts | at most one provider call and one receipt |
| Stale lease/fence | pre-submit refusal |
| Wrong worker/epoch/generation | conflict/refusal |
| Receipt symlink/multi-link/wrong owner | refusal |
| Receipt partial/non-canonical/digest drift | refusal |
| Process dead, wait task pending | cleanup incomplete; no Attempt completion |
| Partial stream capture | completeness=false remains visible |
| Worker/provider unavailable | no cross-carrier failover |
| Stage-B unavailable | materialization test remains independent; no target assignment |

## 10. Real production canary

Use one disposable, read-only planner. Inject a control response loss after worker receipt durability.
The canary passes only if:

1. exactly one Job and one Attempt exist;
2. one provider start command and one `thread/start` occur;
3. an immutable receipt exists with an exact digest;
4. restart/status reconciliation imports the same receipt;
5. G1 bind becomes durable;
6. when forced, G2 resumes the same `provider_session_id`;
7. one harmless turn returns a typed result;
8. all cleanup ownership facts are terminal;
9. no second provider thread, Attempt, worker, target or lifecycle record exists;
10. RET1 sees the terminal candidate;
11. production configuration returns to disarmed after the bounded ceremony.

## 11. Stop condition

Stop after exact-head source implementation, hosted security/test proof and independent review are
complete. Return to Sol. Do not merge, arm production, run the canary, start Stage B, or absorb
provider-neutral generalization.

## 12. Continuation handoff

The return packet must state:

```text
operation and PR
protected MAT-F0 merge SHA
implementation base/head
exact changed files
receipt schema/path/digest law
normal/lost/restart provider call counts
effect-unknown and missing-receipt behavior
teardown ownership proof
hosted checks
independent verdict
what merge would and would not make true
exact canary gate
```
