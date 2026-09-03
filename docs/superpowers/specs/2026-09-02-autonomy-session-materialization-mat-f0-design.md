# MAT-F0 — Durable, effect-certain Executive session materialization

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

Mastermind does **not** need a new “session materialization service,” session database, lifecycle
machine, queue, scheduler, target registry, retry plane, or provider router.

Most of the materialization journey already exists behind the default-off Executive Operator Harness:

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

The missing capability is narrower and more important:

> When the provider process and thread were created but the control-side reply or Runtime bind was
> lost, recover the exact same materialization—or quarantine and clean it up—without issuing another
> `thread/start`, creating another Attempt, or inventing another truth store.

The first vertical remains deliberately narrow: one already-admitted, exact-command-bound,
read-only `plan` Job on the existing Codex App Server worker realm. General worker roles, another
provider family, autonomous target assignment, cross-alias transfer, and ChatGPT-Web conversation
creation remain separate waves.

This architecture adopts and hardens the existing producer path. It does not replace it.

## 1. Outcome and completion standard

### User outcome

The Chairman can submit one bounded Executive objective and have Mastermind create the required
execution surface without personally opening a Codex session or relaying messages.

### Machine outcome

For one exact Executive Attempt, the system can prove all of the following:

1. one deterministic dispatch command claimed one Attempt;
2. one deterministic materialization command authorized at most one provider start submission;
3. the exact worker, epoch, process generation, provider process, provider thread, profile,
   attestation, and principal observations are recoverable after a lost response;
4. the same materialization can be bound into Executive Runtime without another provider start;
5. a restart either resumes the same provider thread through the existing G2 path or leaves the same
   Attempt explicitly quarantined;
6. terminal success is impossible until process, writer, owned resources, wait tasks, monitors,
   stream pumps, and receipt completeness all reach an accepted terminal disposition.

### Real completion proof

MAT-C1 is not complete merely because tests pass or code merges. Completion requires one disposable,
production-path Codex canary that creates exactly one process and one root provider thread, executes
one harmless read-only turn, returns one typed result, survives an injected response-loss boundary,
reconciles without a second `thread/start`, and proves full teardown.

## 2. Capability ledger at the protected basis

| Capability | State | Evidence / limit |
|---|---|---|
| Executive Job/Attempt/Worker/Event lifecycle, lease and fence | `BUILT_NOT_PROVEN` | Existing Runtime v4; production arming is separate |
| Exact command-bound planner dispatch | `BUILT_NOT_PROVEN` | `dispatch_cycle_job()` and service COO cycle; default-off |
| Pre-provider Runtime start INTENT and dispatch commitment | `BUILT_NOT_PROVEN` | OHF reserve/dispatch receipts exist |
| Codex App Server process + root thread creation | `BUILT_NOT_PROVEN` | Existing broker/adapter path; default-off |
| Control-side bind, attestation and principal admission | `BUILT_NOT_PROVEN` | Existing TX-3 / admission path |
| Same-Attempt G1 recovery and G2 native resume after a bound generation | `BUILT_NOT_PROVEN` | Existing `reconcile_restart()` path |
| Durable terminal-return reduction | `BUILT_NOT_PROVEN` | RET1 protected; production projection remains separately gated |
| Lost-response recovery after provider start but before Runtime bind | `NOT_BUILT` | No immutable worker materialization receipt or exact status read |
| Broker-restart recovery of an unbound provider start | `NOT_BUILT` | Worker `_operator_run` is process-local |
| Full teardown lifecycle including wait/monitor/pipe disposition | `PARTIAL` | Process-group absence alone is insufficient; teardown carrier remains held |
| General role/provider materialization | `NOT_BUILT` | First vertical is Codex read-only planner only |
| Stage-B action-authoritative target assignment | `SPEC_ONLY` | Separate responsibility/alias authority; must not be smuggled into MAT-C1 |
| Unattended end-to-end production autonomy | `NOT_BUILT` | Requires later Wake/ACK/terminal-return/assignment proof |

## 3. Canonical ownership

| Fact or effect | Canonical owner | MAT-F0 rule |
|---|---|---|
| Job, Attempt, Worker, status, lease, fence, command and Event | Executive Runtime | Sole lifecycle and durable mutation authority |
| Concrete worker/quota selection | Existing Executive dispatch/Capacity owner | Materialization consumes an exact selected Attempt; it does not select capacity |
| Capability/profile/model/sandbox contract | Model Router + ExecutionCapabilityRegistry + Attempt effective grant | Revalidated before provider submission; model output grants nothing |
| Start/resume/turn/stop operation ordering | OperatorHarnessOrchestrator + ExecutiveOperatorHarnessPort | Preserve command-first Runtime receipt before every provider mutation |
| Actual provider process/thread effect | Worker broker + CodexOperatorAdapter | Provider I/O stays outside the Runtime transaction |
| Lost-response materialization evidence | Existing worker `run_root`, through one immutable typed receipt | Evidence only; never lifecycle/currentness/authority |
| Exact current binding projection | RuntimeBinding projection | Read-only projection after accepted Runtime bind |
| Root responsibility → logical Sol alias | Stage B / SessionTarget authority | Explicitly outside MAT-C1 |
| Wake delivery and consumption ACK | Wake/ACK owners | Downstream consumer; not a materialization prerequisite for initial assignment |
| Terminal candidate reduction | RET1 | Consumes terminal Runtime evidence; does not create or clean sessions |
| Cross-session organizational continuity | Agent OS | Records the ruling/handoff, never provider or lifecycle truth |
| Code and immutable proof | GitHub | Exact implementation/evidence truth |
| Slack dialogue | Slack | Transport only; no materialization authority |

## 4. Current-source archaeology and the exact gap

The protected source already enforces the safe side of the boundary:

1. `ExecutiveOperatorSupervisor.start_cycle_job()` accepts only an exact planner Job and delegates
   the exact command-bound claim to Executive Runtime.
2. `OperatorHarnessOrchestrator.start_attempt()` validates the requested profile, seals the Attempt,
   extends the lease, commits the Runtime start INTENT/writer fence, commits provider dispatch, and
   only then calls the provider adapter.
3. `ExecutiveOperatorHarnessPort` maps every operation onto existing Runtime methods; it owns no
   state.
4. `ExecutiveWorkerBroker` runs under a distinct worker UID and accepts only typed AF_UNIX requests.
5. `CodexOperatorAdapter` starts one private App Server process, validates effective configuration,
   calls `thread/start`, requires an exact root thread and `thread/started` confirmation, and keeps
   generation state in memory.
6. The orchestrator records durable `EFFECT_UNKNOWN` when provider start or subsequent bind cannot
   be safely reconciled from the immediate response.
7. `ExecutiveOperatorSupervisor.reconcile_restart()` never cross-Attempt requeues. It can recover an
   exact **already-bound** generation and resume the same provider session through G2.

The gap is between items 5 and 7:

```text
Runtime start INTENT + provider-dispatch commitment
→ provider process/thread successfully created
→ control reply lost OR Runtime bind failed
→ worker has process-local state
→ Runtime has no provider_session_id/process identity
```

The current recovery method requires the Runtime generation already to contain exact process and
provider-session identity. The worker broker’s `_operator_run` is process-local and is lost on broker
restart. The provider declares no native idempotency for `thread/start`. Reissuing start is therefore
forbidden.

This state is `MATERIALIZED_UNBOUND`.

## 5. Chosen architecture: one immutable worker evidence receipt

MAT-C1 adds one typed, immutable, secret-safe **materialization evidence receipt** under the existing
worker `BrokerPolicy.run_root`. This is not a store of current state and not a lifecycle authority.

### 5.1 Fixed evidence location

The worker derives the location; no caller supplies a path:

```text
<BrokerPolicy.run_root>/
  .operator-materializations/
    <sha256(operation_command_id)>/
      receipt.json
```

The directory and file must be non-symlink, single-link where applicable, worker-owned, mode 0700/0600,
and created with exclusive create plus file and parent-directory `fsync`. Existing content is never
overwritten. A semantic mismatch at the same command identity is a conflict.

The receipt remains evidence after import. Deleting it early must never be required for correctness.
Retention may later be bounded by a separate evidence-retention policy after terminal proof; MAT-C1
does not invent one.

### 5.2 Receipt content

The receipt schema is `mastermind.operator_materialization_receipt/v1` and contains exactly:

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

`receipt_digest` is SHA-256 over canonical receipt bytes with that field omitted.

The receipt contains no token, credential, auth file content, raw model output, prompt, transcript,
Slack principal, account email, Job objective, branch, worktree contents, or arbitrary filesystem
path. The typed provider-home observation may contain only the already-reviewed identity fields
currently admitted by the principal contract.

The receipt does not say that the Attempt is current, authoritative, complete, successful, or
eligible. Those facts remain Runtime-derived.

### 5.3 Write point

The worker persists the receipt:

1. after `thread/start` or `thread/resume` returns an exact provider session;
2. after the adapter has validated root-session identity and collected typed attestation, process
   credentials, and provider-home identity;
3. before the worker broker returns success to the control process;
4. before the control process attempts Runtime bind.

If persistence fails after provider creation, the broker must not report success. It performs at most
one bounded same-process cleanup attempt, reports effect uncertainty, and never starts again under a
new command.

### 5.4 Read path

MAT-C1 adds one read-only broker operation, conceptually
`ohf-materialization-status`, accepting only the exact operation command, Attempt, epoch, and process
generation identities. It may return:

```text
ABSENT
RECEIPT_CURRENT_IN_LIVE_BROKER
RECEIPT_ONLY_AFTER_RESTART
CONFLICT
```

It performs no provider start, resume, turn, stop, cancel, target assignment, lease mutation, or
Runtime mutation.

A duplicate `ohf-start` with the same identity may return the same receipt when the worker can prove
exact semantic equality, but the control-side reconciliation path must use the read-only status
operation rather than blindly resubmitting the modifying call.

## 6. Machine-readable architecture freeze

<!-- MAT_F0_CONTRACT_BEGIN -->
```json
{
  "schema": "mastermind.session_materialization_f0_contract.v1",
  "operation": "autonomy-session-materialization-mat-f0-architecture-freeze-20260902-sol-001",
  "protected_source_sha": "2c59fc6a987b02b2ca3db4e59fb90a5246eaed12",
  "records_wave": "MAT-F0",
  "records_state_after_merge": "SPEC_ONLY / RECORDS_ONLY / PRODUCTION_INERT / PROTECTED",
  "implementation_wave": "MAT-C1",
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
    "control_plane.executive_worker_broker.ExecutiveWorkerBroker",
    "control_plane.codex_operator_adapter.CodexOperatorAdapter"
  ],
  "lifecycle_authority": "control_plane.executive_runtime",
  "outer_dispatch_command": "coo-cycle:<root_job_id>:dispatch:<job_id>:attempt:<attempt_number>",
  "materialization_operation_command": "ohf-op:start:<attempt_id>",
  "provider_call_inside_runtime_transaction": false,
  "provider_native_idempotency": false,
  "worker_receipt": {
    "schema": "mastermind.operator_materialization_receipt/v1",
    "authority": "EVIDENCE_ONLY",
    "root_owner": "control_plane.executive_worker_broker.BrokerPolicy.run_root",
    "path": ".operator-materializations/<sha256(operation_command_id)>/receipt.json",
    "write_owner": "control_plane.executive_worker_broker.ExecutiveWorkerBroker",
    "read_owner": "exact typed broker status operation",
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
  "derived_states": [
    "PRE_SUBMIT_REFUSED",
    "DISPATCH_COMMITTED_UNOBSERVED",
    "MATERIALIZED_UNBOUND",
    "BOUND_CURRENT",
    "RUNNING_TURN",
    "TERMINAL_RESULT_SEALED",
    "TERMINAL_RELEASED",
    "CLEANUP_INCOMPLETE",
    "MATERIALIZATION_IDENTITY_UNKNOWN",
    "EFFECT_UNKNOWN"
  ],
  "materialized_unbound_formula": [
    "exact Runtime start INTENT exists",
    "exact Runtime provider-dispatch commitment exists",
    "exact immutable worker materialization receipt exists",
    "matching Runtime bind/APPLIED receipt is absent"
  ],
  "normal_order": [
    "revalidate service, autonomy, worker, capability and workspace identities",
    "claim one exact Attempt with the existing dispatch command",
    "reserve the existing Runtime epoch and generation",
    "commit the existing provider-dispatch receipt",
    "call provider outside the Runtime transaction",
    "validate process, root provider session, attestation and principal evidence",
    "persist the immutable worker receipt before replying",
    "validate and import the receipt into the existing Runtime bind path",
    "seal attestation and principal evidence",
    "project RuntimeBinding read-only",
    "execute one bounded turn",
    "seal result",
    "prove complete teardown",
    "abandon epoch and terminalize the same Attempt",
    "project terminal return through RET1"
  ],
  "effect_unknown_law": {
    "same_carrier": true,
    "status_read_before_any_modifying_replay": true,
    "blind_retry": false,
    "cross_worker_failover": false,
    "second_attempt": false,
    "second_provider_start": false,
    "missing_receipt_after_dispatch": "MATERIALIZATION_IDENTITY_UNKNOWN / QUARANTINE"
  },
  "restart_law": {
    "receipt_exists": "bind the exact historical G1 evidence, reconcile the exact process, then use existing same-session G2 resume when lawful",
    "receipt_missing": "do not recreate; preserve effect uncertainty and quarantine the same Attempt",
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
  "next": "MAT-C1_EFFECT_CERTAIN_UNBOUND_RECEIPT_AND_RECONCILIATION"
}
```
<!-- MAT_F0_CONTRACT_END -->

The JSON block is normative. Prose may explain it but may not widen it.

## 7. State derivation

These labels are projections over existing Runtime Events plus the worker receipt. They are not new
database enums.

### `PRE_SUBMIT_REFUSED`

The profile, identity, capacity, lease, workspace, authority, or configuration gate refused before
provider-dispatch commitment. A later corrected operation may be considered under the owning
command/retry law because no provider effect began.

### `DISPATCH_COMMITTED_UNOBSERVED`

The Runtime provider-dispatch commitment exists, but neither a worker receipt nor a Runtime bind is
currently observable. This is not proof that no provider call occurred.

### `MATERIALIZED_UNBOUND`

The exact worker receipt proves provider materialization, while the Runtime bind/APPLIED receipt is
absent. This is recoverable under the same operation and generation; it is never permission to start
again.

### `BOUND_CURRENT`

The existing Runtime bind, attestation, principal admission, lease, fence, epoch, and current writer
all validate. RuntimeBinding may now be projected read-only.

### `MATERIALIZATION_IDENTITY_UNKNOWN`

Provider dispatch committed, no exact worker receipt exists, and the effect cannot be reconstructed.
The same Attempt remains quarantined. Local process absence does not prove remote thread absence.

### `CLEANUP_INCOMPLETE`

The provider process may be absent, yet one or more owned wait/monitor/stream/resource tasks or
capture-completeness facts remain unresolved. No successful terminal Attempt is allowed.

## 8. Exact normal sequence

1. The service revalidates current autonomy receipt, installed configuration, worker identity,
   capability profile, workspace identity, and exact base.
2. Existing Executive dispatch creates/returns one command-bound Attempt and lease.
3. The supervisor derives `ohf-op:start:<attempt_id>`.
4. Runtime reserves the session epoch and G1 process generation under the Attempt lease/fence.
5. Runtime commits provider dispatch for that exact operation.
6. The control-side proxy sends one typed `ohf-start` request to the exact worker broker.
7. The worker broker first checks the derived receipt path and active generation identity.
8. With no prior receipt/state, the worker creates one adapter/resource and calls provider start.
9. The Codex adapter validates one private App Server process, one exact root provider thread, and the
   effective profile.
10. The worker broker gathers typed start, attestation, process-principal, and provider-home facts.
11. The worker broker writes and fsyncs the immutable receipt.
12. Only then does it return the typed receipt to the control side.
13. The control side validates the receipt against the leased Attempt, operation, epoch, generation,
   expected profile digest, worker, and current Runtime command receipts.
14. Existing Runtime bind/APPLIED and attestation/principal admission commit.
15. RuntimeBinding is projected; no target assignment occurs.
16. One bounded turn executes.
17. The role result is sealed.
18. Stop/cancel/reconcile proves dead/released plus complete owned-task/resource/pipe disposition.
19. The epoch is abandoned and the same Attempt terminalizes.
20. RET1 may project the typed terminal candidate.

## 9. Lost-response and restart reconciliation

### 9.1 Worker receipt exists; broker still owns the live generation

The control-side failure records `EFFECT_UNKNOWN`. Reconciliation reads the exact materialization
status. The broker returns the existing receipt and live identity without another provider call.
The control validates and binds that receipt, then continues the same Attempt.

### 9.2 Worker receipt exists; broker restarted

The new broker validates the immutable receipt from its fixed run root. It does not reconstruct
lifecycle state or claim the generation current. The control validates and binds the historical G1
start evidence. Existing process reconciliation then determines:

- exact process still alive but transport ownership lost → bounded exact cleanup, then dead/released;
- exact process dead/released → preserve that observation;
- identity mismatch or ambiguous process → quarantine.

Once G1 is exactly bound and proven released, the existing G2 native-resume path may resume the same
`provider_session_id`. It must not call `thread/start`.

### 9.3 Dispatch committed; receipt absent

This remains `MATERIALIZATION_IDENTITY_UNKNOWN`. The broker may perform its existing UID sweep and
prove local process quiescence, but that does not prove a remote provider thread was never created.
The system must not start, resume an unknown ID, create another Attempt, or fail over. A human or
future provider-side reconciliation owner may resolve it; MAT-C1 does not fabricate one.

### 9.4 Same command with changed semantics

Any mismatch in Attempt, worker, epoch, generation, requested-profile digest, operation kind, or
provider identity is `MATERIALIZATION_RECEIPT_CONFLICT`. No overwrite, adoption, or second effect.

## 10. Concurrency and exactly-once claims

MAT-C1 may claim:

- exactly one Executive Attempt for the exact dispatch command;
- at most one provider start **submission** for the exact materialization command while the reviewed
  worker receipt and broker exclusion rules hold;
- no blind retry after an uncertain provider effect;
- deterministic reconciliation of an existing receipt.

MAT-C1 must not claim:

- distributed exactly-once provider execution under arbitrary host power loss;
- provider-native idempotency;
- proof that no orphan remote thread exists when dispatch committed but no receipt survived;
- successful cleanup from process-group absence alone;
- autonomous responsibility assignment.

A crash after provider effect but before receipt durability can leave an unknown orphan. The correct
response is fail-closed quarantine, not a second start.

## 11. Teardown and capture truth

The held teardown finding is incorporated as architecture:

```text
process group absent
≠ wait task finished
≠ monitor finished
≠ inherited stdout/stderr descriptors closed
≠ complete capture
≠ safe terminal Attempt
```

Every owned asynchronous/process resource must be either:

```text
COMPLETED
CANCELLED_AND_JOINED
```

A pending task may not be silently abandoned, reclassified as detached success, or hidden behind a
bounded wait timeout. If an accepted future shared reaper owns such tasks, that transfer must have a
named durable receipt and independent source law; MAT-C1 creates no reaper.

Partial output is recorded as partial. Byte counts/digests and a completeness bit must not be
upgraded after an interrupted drain.

## 12. Authority and separation laws

1. Receipt possession grants no Job, Attempt, target, retry, merge, release, or Chairman authority.
2. The worker cannot select another Worker, quota class, account, model, provider, or Attempt.
3. The control cannot accept a receipt whose worker/profile/epoch/generation differs from the current
   command-bound Attempt.
4. Stage B remains the only future owner of durable root responsibility → logical alias assignment.
5. RuntimeBinding remains a projection from accepted current Runtime evidence; the receipt does not
   become a binding row.
6. Wake/ACK remains downstream attention/consumption. Initial materialization does not require a
   circular Wake ACK.
7. Terminal return is not provider cleanup and provider cleanup is not terminal return.
8. Slack delivery or provider UI visibility proves none of these states.
9. Model prose cannot originate a provider call, receipt, bind, retry, or cleanup decision.

## 13. Failure taxonomy

| Failure | Required state/action |
|---|---|
| Profile/identity/workspace/config refusal before dispatch | `PRE_SUBMIT_REFUSED`; zero provider call |
| Dispatch commit response lost | Query Runtime command; do not resend through another carrier |
| Worker unavailable before request write | no provider effect; preserve same command |
| Worker timeout after request write | `EFFECT_UNKNOWN`; query materialization status |
| Receipt exists and matches | import/bind same generation |
| Receipt exists but differs | `CONFLICT`; no adoption or overwrite |
| Receipt missing after dispatch | `MATERIALIZATION_IDENTITY_UNKNOWN`; quarantine |
| Broker restart with receipt | validate receipt; bind/reconcile G1; optionally resume same thread as G2 |
| Broker restart without receipt | never create; local sweep is not remote-thread absence |
| Process identity mismatch | quarantine; no kill/adopt by guessed PID |
| Provider session differs on resume | conflict; no continuation |
| Lease/fence moved | refuse stale actor |
| Teardown task or pipe pending | `CLEANUP_INCOMPLETE`; no successful terminalization |
| Response ambiguity after Runtime bind | reconcile existing Runtime command; no second bind/start |
| Capacity loss after START | return through current Capacity/Attempt reconciliation; no account hopping |

## 14. Security and data boundaries

- Receipt serialization is strict canonical JSON with exact key sets and bounded byte size.
- All nested typed values are validated by their existing wire contracts before persistence and
  again before import.
- Receipt paths are derived from SHA-256 of the operation command; caller path input is forbidden.
- Symlink components, multi-link files, wrong owner/mode, partial JSON, digest mismatch, duplicate
  keys, unknown keys, and non-canonical bytes refuse.
- Provider credentials remain only in the dedicated provider home and are never read into the
  receipt.
- Raw provider stdout/stderr, transcript content, prompts, and model results do not enter the receipt.
- Error messages crossing AF_UNIX remain fixed, bounded, and secret-safe.
- Receipt reads are exact identity lookups, not directory scans that elect “latest.”
- Wall-clock timestamps never elect current materialization.

## 15. Architecture freeze and no-rebuild boundary

MAT-C1 may add one pure typed receipt contract/helper and extend the existing broker, remote adapter,
and supervisor. It may not add:

- a materialization database/table;
- a new Job/Attempt/Worker/Event lifecycle;
- a “current sessions” registry;
- another lease/fence;
- a retry queue;
- a provider-selection router;
- a target-assignment store;
- a daemon or scheduler per materialization;
- an out-of-band process launcher;
- a Slack-driven start path;
- an automatic second Attempt;
- a generic shell/API endpoint.

The existing service, dispatch, OHF port, Runtime, worker broker, and provider adapter remain the
canonical path.

## 16. Implementation boundary

The expected MAT-C1 source surface is deliberately small:

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
  tests/test_ohf_p1b_runtime_orchestrator.py   # only if needed for the exact loss seam
```

Protected/no-edit absent a new Sol ruling:

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

If current-source archaeology proves the expected surface cannot implement the contract without an
owner change, return to Sol before widening.

## 17. Dependency and release gates

### MAT-F0 protection

This records-only architecture may be protected independently after exact-head CI and independent
review. It creates no runtime or provider effect.

### MAT-C1 source implementation

MAT-C1 may start only after:

1. MAT-F0 is protected;
2. current-base path collision archaeology is complete;
3. the teardown lifecycle contract represented by the current held teardown carrier is protected or
   MAT-C1 is proven path-disjoint and keeps production proof held;
4. exact current Skillpack and owner contracts are re-pinned.

Capacity C1/C2, Stage B, Wake, ACK, and W3C do not need to be falsely declared complete merely to
implement this bounded source seam.

### Production canary

A production canary additionally requires:

- current host autonomy/secret-canary/identity gates green;
- exact worker/provider home and installed release attested;
- one approved disposable Job/Attempt/profile;
- no overlapping materialization or teardown writer;
- exact cleanup lifecycle protected;
- current production configuration explicitly armed for the canary;
- one independent exact-release review.

The canary does not arm general autonomy.

## 18. Acceptance tests

MAT-C1 must include mutation-discriminating tests for:

1. provider start succeeds, control reply is lost before Runtime bind, status returns the exact
   receipt, and the same G1 binds with **zero second `thread/start`**;
2. broker restarts after receipt durability but before Runtime bind; the receipt imports and the same
   provider session is resumed as G2 without another root thread;
3. dispatch committed but receipt absent; start/resume/failover are refused;
4. same command + changed Attempt/profile/generation conflicts;
5. two concurrent exact starts produce at most one provider call and one receipt;
6. receipt path traversal, symlink, overwrite, multi-link, owner/mode, digest, duplicate-key,
   unknown-key, and partial-write attacks refuse;
7. stale lease/fence, wrong worker, wrong provider home, wrong profile, or wrong workspace refuses
   before provider call;
8. process absent while wait/monitor/stream task remains pending produces `CLEANUP_INCOMPLETE`;
9. partial stream capture remains marked partial;
10. Runtime bind response loss reconciles by command and never restarts provider;
11. receipt cannot mutate Runtime or grant target/authority;
12. Stage-B/session-target files remain unchanged.

## 19. Production proof packet

The real canary return must preserve:

```text
protected release SHA
Job ID
Attempt ID
dispatch command ID
materialization operation command ID
session epoch ID
G1/G2 process generation IDs
worker materialization receipt digest
provider start call count
provider root thread count
Runtime bind/APPLIED command
served model/profile/capability evidence
turn INTENT/APPLIED and typed result
process dead + provider writer released
wait/monitor/stream/resource terminal receipts
UID sweep receipt
terminal Attempt/Event receipt
RET1 candidate identity
proof of zero second Attempt and zero second thread/start
```

Secrets, prompts, transcript text, provider credentials, and raw model output remain excluded.

## 20. Exact next action

After MAT-F0 exact-head review and protection, commission one bounded MAT-C1 worker to implement the
immutable receipt plus same-operation status/import seam on the existing Executive/OHF path. Keep the
current session-materialization recovery child on PRE_START/HOLD until that protected architecture
SHA is posted to its exact Slack carrier.
