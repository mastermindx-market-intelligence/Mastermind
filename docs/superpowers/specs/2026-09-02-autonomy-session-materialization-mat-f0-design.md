# MAT-F0 — Effect-certain Executive session materialization

**Date:** 2026-09-02  
**Owner:** Sol, AI CEO  
**Chairman:** Chris  
**Program:** `autonomy-grokless-finishline-20260831-sol-001`  
**Architecture operation:** `autonomy-session-materialization-mat-f0-architecture-freeze-20260902-sol-001`  
**Protected source / Skillpack basis:** `mastermindx-market-intelligence/Mastermind@2c59fc6a987b02b2ca3db4e59fb90a5246eaed12`, `mastermind.sol_skillpack.v1` 1.0.1, bootstrap major 1  
**Records wave:** `MAT-F0`  
**First implementation wave:** `MAT-C1`  
**State:** `SPEC_ONLY / RECORDS_ONLY / PRODUCTION_INERT / HOLD-FOR-SOL`

## 0. Executive ruling

Mastermind does **not** need another session service, session database, lifecycle machine, queue,
scheduler, target registry, retry plane, or provider router.

The real default-off producer already exists:

```text
ExecutiveControlService
→ ExecutiveOperatorSupervisor
→ OperatorHarnessOrchestrator
→ ExecutiveOperatorHarnessPort
→ Executive Runtime Job / Attempt / Event / lease / fence
→ RemoteCodexOperatorAdapter
→ ExecutiveWorkerBroker
→ CodexOperatorAdapter
→ Codex App Server process + provider thread
```

The missing capability is effect-certain reconciliation at two symmetric boundaries:

```text
G1: thread/start succeeds → worker reply or Runtime TX-3 bind is lost
G2: thread/resume succeeds → worker reply or Runtime TX-11 bind is lost
```

Neither boundary may issue the provider call again. The system must recover the exact observed
materialization, or quarantine and clean it up, while preserving the same Executive Attempt and
operation identity.

The first vertical is one command-bound, read-only `plan` Attempt on `openai-codex` /
`codex-app-server`. General roles/providers, ChatGPT-Web creation, Stage-B responsibility transfer,
Wake/ACK, and production arming remain separate.

## 1. Outcome and completion

### Chairman outcome

One bounded Executive objective can acquire a real Codex execution surface without the Chairman
opening a session, selecting a numbered account, or relaying a handoff.

### Machine outcome

For one exact Attempt, Mastermind can prove:

1. one deterministic dispatch command claimed one Attempt;
2. G1 start and G2 resume each use one deterministic provider-operation command;
3. a successful provider process/thread observation survives a lost control response;
4. the observation is imported through existing Runtime TX-3 or TX-11, never a parallel binding;
5. currentness is re-derived from Runtime lease/fence/epoch/generation evidence, not from the receipt;
6. committed dispatch with no receipt remains effect-unknown and cannot be retried;
7. no successful terminal result exists until complete process/resource/task/pipe teardown is proven.

### Real proof

MAT-C1 is not complete at merge. Production proof requires one disposable read-only canary that:

- creates one G1 process and one root provider thread;
- loses a control response after the G1 receipt is durable;
- imports and binds that same G1 with zero second `thread/start`;
- proves G1 dead/released and allocates the existing lawful G2 resume;
- loses a control response after the G2 receipt is durable while the broker still owns G2;
- imports and binds that same G2 with zero second `thread/resume` and zero `thread/start`;
- executes one harmless turn and returns one typed result;
- proves complete teardown and zero second Attempt.

A separate restart test must prove receipt-only G2 reconciliation after broker restart. Because current
OHF permits no G3, a dead G2 after restart may terminalize or remain quarantined; it may not be
presented as a successful continuation.

## 2. Capability ledger at the protected basis

| Capability | State | Limit |
|---|---|---|
| Executive Job/Attempt/Worker/Event lifecycle, lease, fence | `BUILT_NOT_PROVEN` | production arming separate |
| Exact command-bound planner dispatch | `BUILT_NOT_PROVEN` | default-off |
| Runtime start/resume INTENT and provider-dispatch commitment | `BUILT_NOT_PROVEN` | existing OHF path |
| Codex App Server `thread/start` and `thread/resume` | `BUILT_NOT_PROVEN` | provider-native idempotency false |
| TX-3 start bind, TX-11 resume bind, TX-4 admission | `BUILT_NOT_PROVEN` | exact Runtime owner |
| Bound G1 recovery and lawful same-session G2 resume | `BUILT_NOT_PROVEN` | no G3 |
| RET1 terminal-return reduction | `BUILT_NOT_PROVEN` | production projection gated |
| Lost G1 response before TX-3 | `NOT_BUILT` | no durable worker receipt/status import |
| Lost G2 response before TX-11 | `NOT_BUILT` | same missing seam |
| Broker-restart recovery of unbound G1/G2 | `NOT_BUILT` | worker active state is process-local |
| Complete task/resource/pipe teardown | `PARTIAL` | process absence alone insufficient |
| Stage-B action-authoritative target assignment | `SPEC_ONLY` | separate owner |
| General unattended autonomy | `NOT_BUILT` | later end-to-end proof required |

## 3. Canonical ownership

| Fact/effect | Canonical owner | MAT-F0 rule |
|---|---|---|
| Job, Attempt, lease, fence, command, Event, current epoch/writer | Executive Runtime | sole lifecycle authority |
| Worker/quota selection | existing dispatch/Capacity owner | materialization consumes selection |
| Requested profile/effective grant | capability policy + Attempt | revalidated before provider I/O |
| Operation ordering | OperatorHarnessOrchestrator + ExecutiveOperatorHarnessPort | Runtime intent/dispatch first |
| Provider process/thread effect | worker broker + CodexOperatorAdapter | outside Runtime transaction |
| Lost-response observation | immutable worker receipt under existing `BrokerPolicy.run_root` | evidence only |
| G1/G2 bind and admission | existing TX-3/TX-11/TX-4 | no new Runtime transaction type by default |
| RuntimeBinding | existing projection | only after accepted Runtime bind |
| Root responsibility → Sol alias | Stage B / SessionTarget authority | outside MAT-C1 |
| Wake/ACK | Wake owners | downstream, separate |
| Terminal reduction | RET1 | not cleanup or materialization |
| Organizational continuity | Agent OS | not execution truth |
| Code/proof | GitHub | exact implementation truth |
| Slack | transport | no lifecycle or target authority |

## 4. Exact current gap

Protected source already performs the safe ordering:

1. exact planner dispatch creates one Attempt and lease;
2. `start_attempt()` reserves G1, commits provider dispatch, then calls the worker;
3. `resume()` reserves G2, commits provider dispatch, then calls the worker;
4. worker `ohf-start` and `ohf-resume` both enter `_ohf_start(..., resume=<bool>)`;
5. `CodexOperatorAdapter` validates one private App Server process and the exact provider session;
6. Runtime records `EFFECT_UNKNOWN` when provider I/O may have occurred but bind/response is lost;
7. `reconcile_restart()` never creates a second Attempt, but it requires already-bound identity.

The unbound gaps are:

```text
G1_UNBOUND:
  start INTENT + dispatch commitment + provider start observation
  + no TX-3 APPLIED

G2_UNBOUND:
  resume INTENT + dispatch commitment + provider resume observation
  + no TX-11 APPLIED
```

The broker’s active operator state is process-local. A broker restart loses current adapter ownership.
The provider exposes no start idempotency. Reissuing either call is forbidden.

## 5. Immutable worker evidence receipt

MAT-C1 adds one typed, immutable, secret-safe receipt contract. Each modifying provider operation has
its own receipt, derived from the exact operation command:

```text
<BrokerPolicy.run_root>/
  .operator-materializations/
    <sha256(operation_command_id)>/
      receipt.json
```

The path is worker-derived. Caller-supplied paths, “latest” scans, mtimes, and directory order are
forbidden.

### 5.1 Receipt schema

`mastermind.operator_materialization_receipt/v1` contains exactly:

```text
schema
operation_command_id
operation_kind = start_session | resume_session
attempt_id
worker_id
session_epoch_id
process_generation_id
generation_number
requested_profile_digest
provider_session_id
process_identity
observed_attestation
process_credentials
provider_home_identity
created_at
receipt_digest
```

The receipt contains no credentials, tokens, auth contents, prompt, transcript, raw model output,
Slack principal, account email, Job objective, branch, or arbitrary path. Typed principal/home fields
use only the already-reviewed secret-safe wire shapes.

The receipt grants no currentness, lifecycle state, authority, target, retry, completion, or cleanup
claim.

### 5.2 Durability

Within the broker’s existing exact-operation exclusion boundary:

1. validate profile and exact operation identity;
2. check for an existing receipt before provider I/O;
3. perform `thread/start` or `thread/resume` once;
4. validate provider session, process, attestation, process credentials, and provider-home identity;
5. exclusive-create worker-owned 0700 directories and 0600 receipt;
6. write canonical bytes, `fsync` file and newly material parent directories;
7. reopen and validate exact bytes;
8. only then publish process-local active state and return success.

Existing receipt + exact semantics is reconciliation, not another provider call. Existing receipt +
different semantics is conflict. A persistence failure after provider effect triggers at most one
same-process cleanup attempt and remains effect-unknown.

### 5.3 Read-only status

One exact broker read, conceptually `ohf-materialization-status`, accepts:

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

It returns exactly:

```text
ABSENT
RECEIPT_CURRENT_IN_LIVE_BROKER
RECEIPT_ONLY_AFTER_RESTART
CONFLICT
```

It performs no provider, Runtime, lease, target, retry, stop, or cleanup mutation.

## 6. Normative architecture freeze

<!-- MAT_F0_CONTRACT_BEGIN -->
```json
{
  "schema": "mastermind.session_materialization_f0_contract.v2",
  "operation": "autonomy-session-materialization-mat-f0-architecture-freeze-20260902-sol-001",
  "protected_source_sha": "2c59fc6a987b02b2ca3db4e59fb90a5246eaed12",
  "records_wave": "MAT-F0",
  "implementation_wave": "MAT-C1",
  "records_state_after_merge": "SPEC_ONLY / RECORDS_ONLY / PRODUCTION_INERT / PROTECTED",
  "first_vertical": {
    "provider": "openai-codex",
    "surface": "codex-app-server",
    "job_role": "plan",
    "authority": ["READ"],
    "write_capable": false,
    "production_armed": false
  },
  "canonical_control_chain": [
    "control_plane.executive_service.ExecutiveControlService",
    "control_plane.executive_operator_supervisor.ExecutiveOperatorSupervisor",
    "control_plane.operator_harness_orchestrator.OperatorHarnessOrchestrator",
    "control_plane.executive_operator_harness_port.ExecutiveOperatorHarnessPort",
    "control_plane.executive_runtime"
  ],
  "canonical_worker_chain": [
    "control_plane.remote_codex_operator_adapter.RemoteCodexOperatorAdapter",
    "control_plane.executive_worker_broker.ExecutiveWorkerBroker._ohf_start",
    "control_plane.codex_operator_adapter.CodexOperatorAdapter"
  ],
  "lifecycle_authority": "control_plane.executive_runtime",
  "outer_dispatch_command": "coo-cycle:<root_job_id>:dispatch:<job_id>:attempt:<attempt_number>",
  "materialization_operation_commands": {
    "start_session": "ohf-op:start:<attempt_id>",
    "resume_session": "ohf-op:recover-resume:<attempt_id>"
  },
  "runtime_bind_owners": {
    "start_session": "TX-3 / bind_start_result",
    "resume_session": "TX-11 / bind_resume_result",
    "attestation_and_principal": "TX-4 / seal_attestation"
  },
  "provider_call_inside_runtime_transaction": false,
  "provider_native_idempotency": false,
  "maximum_generation": 2,
  "worker_receipt": {
    "schema": "mastermind.operator_materialization_receipt/v1",
    "authority": "EVIDENCE_ONLY",
    "root_owner": "control_plane.executive_worker_broker.BrokerPolicy.run_root",
    "path": ".operator-materializations/<sha256(operation_command_id)>/receipt.json",
    "write_owner": "control_plane.executive_worker_broker.ExecutiveWorkerBroker._ohf_start",
    "read_owner": "exact typed broker status operation",
    "operation_kinds": ["start_session", "resume_session"],
    "atomic_create": true,
    "overwrite": false,
    "canonical_digest": true,
    "max_bytes": 262144,
    "fields": [
      "schema",
      "operation_command_id",
      "operation_kind",
      "attempt_id",
      "worker_id",
      "session_epoch_id",
      "process_generation_id",
      "generation_number",
      "requested_profile_digest",
      "provider_session_id",
      "process_identity",
      "observed_attestation",
      "process_credentials",
      "provider_home_identity",
      "created_at",
      "receipt_digest"
    ],
    "forbidden_authority": [
      "Job status",
      "Attempt status",
      "lease",
      "fence",
      "current worker",
      "current generation",
      "current target",
      "completion",
      "retry permission"
    ]
  },
  "status_read": {
    "provider_effect": false,
    "runtime_effect": false,
    "accepted_states": [
      "ABSENT",
      "RECEIPT_CURRENT_IN_LIVE_BROKER",
      "RECEIPT_ONLY_AFTER_RESTART",
      "CONFLICT"
    ]
  },
  "unbound_formulas": {
    "G1_START_UNBOUND": [
      "exact start INTENT exists",
      "exact start provider-dispatch commitment exists",
      "exact start worker receipt exists",
      "matching TX-3 APPLIED is absent"
    ],
    "G2_RESUME_UNBOUND": [
      "exact resume INTENT exists",
      "exact resume provider-dispatch commitment exists",
      "exact resume worker receipt exists",
      "matching TX-11 APPLIED is absent"
    ]
  },
  "import_law": {
    "G1_START_UNBOUND": [
      "same Attempt lease/fence takeover",
      "validate exact G1 receipt and Runtime command evidence",
      "TX-3 bind exact historical start observation",
      "TX-4 seal exact attestation and principal",
      "reconcile exact process",
      "if dead/released, existing G2 resume may be allocated"
    ],
    "G2_RESUME_UNBOUND": [
      "same Attempt lease/fence takeover",
      "validate bound/released G1 and exact G2 receipt/command evidence",
      "require same provider_session_id as G1",
      "TX-11 bind exact historical resume observation",
      "TX-4 seal exact attestation and principal",
      "recover current G2 directly; never allocate G3"
    ]
  },
  "effect_unknown_law": {
    "same_carrier": true,
    "status_read_before_modifying_replay": true,
    "blind_retry": false,
    "cross_worker_failover": false,
    "second_attempt": false,
    "second_start": false,
    "second_resume": false,
    "missing_receipt_after_committed_dispatch": "MATERIALIZATION_IDENTITY_UNKNOWN / QUARANTINE"
  },
  "restart_law": {
    "G1_receipt_only": "bind and seal historical G1, reconcile process, then resume same provider session as G2 only after dead/released proof",
    "G2_receipt_only": "bind and seal historical G2, reconcile or terminalize it; dead G2 cannot create G3",
    "missing_receipt": "do not recreate; preserve effect uncertainty and quarantine the same Attempt",
    "process_absence_proves_remote_thread_absence": false
  },
  "teardown_acceptance": {
    "process_group_absence_alone": false,
    "required": [
      "process_liveness=PROVEN_DEAD",
      "provider_writer_state=RELEASED",
      "attempt resource stopped and sealed when present",
      "wait task terminal or cancelled-and-joined",
      "monitor task terminal or cancelled-and-joined",
      "stdout and stderr pumps terminal with closed descriptors",
      "capture completeness truthfully recorded",
      "worker UID sweep receipt passing"
    ],
    "incomplete_state": "CLEANUP_INCOMPLETE / NO_ATTEMPT_COMPLETION"
  },
  "stage_b_separate": true,
  "wake_ack_separate": true,
  "capacity_selection_separate": true,
  "no_rebuild": {
    "new_tables": [],
    "new_migrations": [],
    "new_lifecycle_states": [],
    "new_queues": [],
    "new_schedulers": [],
    "new_target_registries": [],
    "new_retry_plane": [],
    "runtime_binding_rows_written_outside_existing_owner": false
  },
  "production_arming": false,
  "next": "MAT-C1_EFFECT_CERTAIN_G1_G2_RECEIPT_AND_RECONCILIATION"
}
```
<!-- MAT_F0_CONTRACT_END -->

The JSON block is normative. Prose may explain but may not widen it.

## 7. Derived states, not new lifecycle states

```text
PRE_SUBMIT_REFUSED
DISPATCH_COMMITTED_UNOBSERVED
G1_START_UNBOUND
G2_RESUME_UNBOUND
BOUND_CURRENT_G1
BOUND_CURRENT_G2
RUNNING_TURN
TERMINAL_RESULT_SEALED
TERMINAL_RELEASED
CLEANUP_INCOMPLETE
MATERIALIZATION_IDENTITY_UNKNOWN
EFFECT_UNKNOWN
```

They are projections over existing Runtime events plus exact receipt evidence. They never become a
new database enum or authority surface.

## 8. Reconciliation

### G1 receipt; broker still owns live G1

Read exact status, validate against current same-Attempt lease/fence and Runtime start command, import
through TX-3 and TX-4, then continue that G1. Zero second start.

### G1 receipt; broker restarted

Import historical G1 through TX-3/TX-4. The receipt does not assert liveness. Use exact
process/UID-sweep reconciliation. If G1 is dead/released, existing G2 may resume the same provider
session. Ambiguity quarantines. Zero second start.

### G2 receipt; broker still owns live G2

Validate bound/released G1, exact resume command, G2 identity, and unchanged provider session. Import
through TX-11/TX-4 and continue that G2 directly. Zero second resume and zero start.

### G2 receipt; broker restarted

Import historical G2 through TX-11/TX-4, then reconcile exact process/resources. If it can be proven
live and still safely owned, continue G2; otherwise stop/terminalize/quarantine it. A dead G2 cannot
allocate G3.

### Committed dispatch; receipt absent

This is `MATERIALIZATION_IDENTITY_UNKNOWN`. Local process absence does not prove no remote thread.
No start, resume, new Attempt, account change, or carrier failover is allowed.

### Receipt conflict

Any mismatch in operation kind/command, Attempt, worker, epoch, generation, profile digest, expected
provider session, process identity, or typed evidence refuses. No overwrite or adoption.

## 9. Teardown law

```text
process group absent
≠ wait task terminal
≠ monitor terminal
≠ inherited stdout/stderr closed
≠ capture complete
≠ safe Attempt completion
```

Every owned task/resource is `COMPLETED` or `CANCELLED_AND_JOINED`. Partial output remains partial.
A shared future reaper would require separate accepted source law; MAT-C1 creates none.

## 10. Security boundaries

- strict canonical JSON, exact key sets, duplicate-key refusal, bounded bytes;
- SHA-256-derived exact path; no caller path or directory scan;
- worker owner/mode, non-symlink and link-count checks;
- exclusive create and no overwrite;
- existing typed nested contracts validated before write and import;
- no secrets, prompts, transcript or raw output;
- fixed bounded AF_UNIX errors;
- no wall-clock/currentness election;
- receipt cannot bypass Runtime command, lease, fence, worker, profile, epoch, or generation checks.

## 11. Implementation boundary

Expected MAT-C1 paths:

```text
Create:
  control_plane/operator_materialization_receipt.py
  tests/test_operator_materialization_receipt.py

Modify:
  control_plane/executive_worker_broker.py
  control_plane/remote_codex_operator_adapter.py
  control_plane/executive_operator_supervisor.py
  tests/test_executive_operator_broker.py
  tests/test_executive_operator_supervisor.py
  tests/test_ohf_p1b_runtime_orchestrator.py   # only if exact loss injection needs it
  tests/test_autonomy_session_materialization_source_law.py
```

The source-law test must transition from protected `NOT_BUILT` characterizations to exact G1/G2
implementation proof while preserving every no-rebuild, no-retry, separation, and teardown law.

Protected absent a new Sol ruling:

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

If existing TX-3/TX-11/TX-4 cannot import exact historical evidence without change, return to Sol;
do not widen Runtime or the orchestrator by convenience.

## 12. Gates

MAT-C1 source work requires:

1. MAT-F0 protected;
2. current-base collision archaeology;
3. current Skillpack and owner re-pin;
4. production proof held if teardown protection is not yet complete.

The production canary additionally requires exact installed release, host identity/autonomy gates,
accepted complete teardown, explicit bounded arming, and independent release review.

## 13. Required discriminators

MAT-C1 must kill these mutations:

1. second `thread/start` after G1 receipt or uncertainty;
2. second `thread/resume` after G2 receipt or uncertainty;
3. G3 allocation;
4. missing receipt interpreted as no effect;
5. receipt treated as currentness/authority;
6. changed profile/Attempt/epoch/generation/provider session adopted;
7. stale lease/fence imports receipt;
8. broker restart calls provider before status/import;
9. process absence completes pending tasks/pipes;
10. partial capture upgraded to complete;
11. Stage B/Capacity/Wake authority imported;
12. source-law test deleted or weakened instead of transitioned.

## 14. Exact next action

After exact-head CI, independent review, and MAT-F0 protection, commission one bounded MAT-C1 source
wave for symmetric G1 start and G2 resume receipts/status/import on the existing Executive/OHF path.
The held session-materialization child remains PRE_START until the protected architecture SHA is
posted to its exact Slack carrier.
