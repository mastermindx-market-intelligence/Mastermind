# MAT-F0 v3 — Effect-certain Executive session materialization

**Date:** 2026-09-03  
**Owner:** Sol, AI CEO  
**Chairman:** Chris  
**Architecture operation:** `autonomy-session-materialization-mat-f0-architecture-freeze-20260902-sol-001`  
**Repair operation:** `autonomy-session-materialization-mat-f0-effect-resolution-repair-20260903-sol-001`  
**Protected source basis:** `Mastermind@caa47c1e66fe36dc3521299c918f4b9e7b2a47ca`  
**State:** `SPEC_ONLY / EFFECT_RESOLUTION_FROZEN / IMPLEMENTATION_HELD / PRODUCTION_INERT`

## 1. Outcome

Starting from one already-admitted Executive planner Attempt and one exact Capacity-selected Worker, the existing Executive/OHF path must create exactly one Codex App Server process and provider thread, survive loss of the worker response before Runtime binding, recover the exact materialized identity without another provider call, run one bounded read-only turn, return through the existing terminal path, and clean up.

This is one crash-consistency repair inside the existing chain:

```text
ExecutiveControlService
→ ExecutiveOperatorSupervisor
→ OperatorHarnessOrchestrator
→ ExecutiveOperatorHarnessPort
→ Executive Runtime
→ RemoteCodexOperatorAdapter
→ ExecutiveWorkerBroker
→ CodexOperatorAdapter
```

The first vertical is only `openai-codex / codex-app-server / plan / READ / no writes`.

## 2. Review blocker and ruling

MAT-F0 v2 incorrectly required a provider response-loss case to be imported through ordinary TX-3/TX-11 after `OPERATOR_OPERATION_EFFECT_UNKNOWN` had already been written. Current Runtime deliberately refuses one operation having both `EFFECT_UNKNOWN` and `APPLIED`; ordinary TX-3 and TX-11 append `APPLIED`, so that path reaches `StateConflict`.

The repaired law is:

```text
normal result:
INTENT → APPLIED

lost response later proved by exact worker receipt:
INTENT → EFFECT_UNKNOWN → RECONCILED(resolution=APPLIED)
```

`EFFECT_UNKNOWN` is immutable history and is never deleted, overwritten, or relabeled. The reconciliation event resolves whether the external effect happened; it does not pretend uncertainty never occurred. The original operation never receives an `APPLIED` event after `EFFECT_UNKNOWN`.

The existing `OperationReceiptKind.RECONCILED`, `:reconciled` command suffix, and `OperationResolution.RECONCILED` vocabulary are reused. No new operation aggregate, table, lifecycle, or retry plane is introduced.

## 3. Authority boundaries

| Fact | Canonical owner |
|---|---|
| Job, Attempt, Worker, lease, fence, Event | Executive Runtime |
| process generation and provider-session binding | existing OHF Runtime rows |
| provider process/thread effect | worker broker + Codex adapter |
| immutable post-effect observation | worker receipt under `BrokerPolicy.run_root` |
| uncertainty resolution | `OperatorHarnessRegistry` transaction |
| current RuntimeBinding projection | `Runtime.current_harness_binding_source` + existing projection |
| placement and eligibility | Capacity |
| logical Sol target assignment | Stage B |
| Wake/ACK/terminal delivery | their existing owners |
| code and proof | GitHub |
| transport visibility | Slack |

The worker receipt is evidence only. It grants no currentness, retry, placement, target, completion, or lifecycle authority. Currentness continues to come from the exact Executive Attempt, lease/fence, CURRENT epoch, current Executive-held generation, work admission, and Runtime rows.

## 4. Normative contract

<!-- MAT_F0_CONTRACT_BEGIN -->
```json
{"candidate_paths":["control_plane/operator_materialization_receipt.py","control_plane/executive_worker_broker.py","control_plane/remote_codex_operator_adapter.py","control_plane/executive_runtime.py","control_plane/executive_operator_harness_port.py","control_plane/executive_operator_supervisor.py","tests/test_operator_materialization_receipt.py","tests/test_executive_operator_broker.py","tests/test_executive_operator_supervisor.py","tests/test_ohf_p1b_runtime.py","tests/test_ohf_p1b_runtime_orchestrator.py","tests/test_runtime_binding_projection.py","tests/test_autonomy_session_materialization_source_law.py"],"capacity_selection_separate":true,"claim":"SPEC_ONLY / EFFECT_RESOLUTION_FROZEN / IMPLEMENTATION_HELD / PRODUCTION_INERT","current_binding_law":{"accepted_lineages":["v1 admission + exact APPLIED terminal receipt","v2 admission + exact EFFECT_UNKNOWN and RECONCILED terminal receipt resolving APPLIED"],"owner":"control_plane.executive_runtime.Runtime.current_harness_binding_source","projection_owner_unchanged":"control_plane.runtime_binding_projection.project_runtime_binding","rejected_lineages":["EFFECT_UNKNOWN without RECONCILED","RECONCILED without EFFECT_UNKNOWN","APPLIED mixed with EFFECT_UNKNOWN or RECONCILED","receipt or admission identity/digest drift","stale Attempt, non-CURRENT epoch, non-current generation, released Executive writer or sealed role result"]},"first_vertical":{"authority":["READ"],"job_role":"plan","production_armed":false,"provider":"openai-codex","surface":"codex-app-server","write_capable":false},"implementation_wave":"MAT-C1","import_law":{"G1_START_UNBOUND":["read exact worker receipt through status; perform no provider call","reconcile_start_result binds the exact historical start observation","append RECONCILED and preserve EFFECT_UNKNOWN; never append APPLIED","TX-4 seals exact attestation and principal","work admission v2 references the exact RECONCILED receipt"],"G2_RESUME_UNBOUND":["read exact worker receipt through status; perform no provider call","reconcile_resume_result validates G1/TX-10 and binds the exact historical resume observation","append RECONCILED and preserve EFFECT_UNKNOWN; never append APPLIED","TX-4 seals exact attestation and principal","recover current G2 directly; never allocate G3"]},"materialization_operation_commands":{"resume_session":"ohf-op:recover-resume:<attempt_id>","start_session":"ohf-op:start:<attempt_id>"},"maximum_generation":2,"next":"MAT-C1_EFFECT_CERTAIN_G1_G2_RECEIPT_AND_RECONCILIATION","no_rebuild":{"new_lifecycle_states":[],"new_migrations":[],"new_queues":[],"new_retry_plane":[],"new_schedulers":[],"new_tables":[],"new_target_registries":[],"runtime_binding_rows_written_outside_existing_owner":false},"operation":"autonomy-session-materialization-mat-f0-architecture-freeze-20260902-sol-001","operation_resolution":{"allowed_success_sets":[["INTENT","APPLIED"],["INTENT","EFFECT_UNKNOWN","RECONCILED"]],"effect_unknown_preserved":true,"forbidden_sets":[["INTENT","EFFECT_UNKNOWN","APPLIED"],["INTENT","APPLIED","RECONCILED"],["INTENT","RECONCILED"],["INTENT","EFFECT_UNKNOWN","RECONCILED","APPLIED"]],"normal_success":{"admission_schema":"mastermind.orchestration_work_admission/v1","effect_unknown":false,"receipts":["INTENT","APPLIED"],"reconciled":false},"ordering":["INTENT","provider-dispatch commitment","EFFECT_UNKNOWN","RECONCILED","TX-4 launch decision","ORCHESTRATION_WORK_ADMITTED"],"reconciled_command_id":"<operation_command_id>:reconciled","reconciled_success":{"admission_schema":"mastermind.orchestration_work_admission/v2","original_applied_receipt":false,"receipts":["INTENT","EFFECT_UNKNOWN","RECONCILED"],"resolution":"APPLIED"},"terminal_election_owner":"control_plane.executive_runtime.OperatorHarnessRegistry._materialization_terminal_receipt"},"production_arming":false,"protected_paths":["control_plane/operator_harness_contract.py","control_plane/operator_harness_orchestrator.py","control_plane/session_targets.py","control_plane/sol_action_target.py","control_plane/runtime_binding_projection.py","control_plane/executive_terminal_return.py","control_plane/wake_*","data/control_plane/*","ops production arming/configuration"],"protected_source_sha":"caa47c1e66fe36dc3521299c918f4b9e7b2a47ca","provider_call_inside_runtime_transaction":false,"provider_native_idempotency":false,"reconciled_payload":{"authority":"EVIDENCE_RESOLUTION_ONLY","fields":["schema_version","operation_kind","resolution","attempt_id","session_epoch_id","process_generation_id","worker_id","provider_session_id","effect_unknown_command_id","materialization_receipt_digest","requested_profile_digest"],"receipt_kind":"RECONCILED","resolution":"APPLIED","schema":"mastermind.operator_materialization_reconciled/v1"},"records_wave":"MAT-F0","repair_operation":"autonomy-session-materialization-mat-f0-effect-resolution-repair-20260903-sol-001","restart_law":{"G1_receipt_only":"reconcile exact G1; if later dead and provider RELEASED, existing TX-10 may resume the same provider session as G1","G2_receipt_only":"reconcile exact G2; continue, stop, terminalize or quarantine; dead G2 cannot create G3","process_absence_proves_remote_thread_absence":false,"worker_receipt_alone_proves_currentness":false},"runtime_normal_bind_owners":{"attestation_and_principal":"TX-4 / OperatorHarnessRegistry.seal_attestation","resume_session":"TX-11 / OperatorHarnessRegistry.bind_resume_result","start_session":"TX-3 / OperatorHarnessRegistry.bind_start_result"},"runtime_reconciliation":{"atomic_effects":["bind the receipt's exact provider session and process identity to the existing epoch/generation rows","set the existing Attempt to RUNNING when reconciling G1","append exactly one OPERATOR_OPERATION_RECONCILED receipt","append no OPERATOR_OPERATION_APPLIED receipt","perform no provider, broker, Slack, Wake or filesystem call inside the Runtime transaction"],"changed_replay":"STATE_CONFLICT","matching_replay":"NO_OP / SAME_RECONCILED_EVENT","missing_receipt":"MATERIALIZATION_IDENTITY_UNKNOWN / QUARANTINE","port_methods":["control_plane.executive_operator_harness_port.ExecutiveOperatorHarnessPort.reconcile_operator_start_result","control_plane.executive_operator_harness_port.ExecutiveOperatorHarnessPort.reconcile_operator_resume_result"],"preconditions":["same current Attempt, lease token and fence generation","exact original INTENT and provider-dispatch commitment","exact EFFECT_UNKNOWN receipt","APPLIED absent","RECONCILED absent or byte-identical replay","exact worker receipt schema, semantic identity and digest","exact sealed requested-profile digest","exact CURRENT epoch and Executive-held generation","G1 generation_number=1 for start","G2 generation_number=2 plus exact TX-10 lineage for resume","G2 provider_session_id equals the immutable G1 epoch session"],"resume_owner":"control_plane.executive_runtime.OperatorHarnessRegistry.reconcile_resume_result","start_owner":"control_plane.executive_runtime.OperatorHarnessRegistry.reconcile_start_result"},"schema":"mastermind.session_materialization_f0_contract.v3","stage_b_separate":true,"supersedes":["mastermind.session_materialization_f0_contract.v1","mastermind.session_materialization_f0_contract.v2"],"teardown_acceptance":{"incomplete_state":"CLEANUP_INCOMPLETE / NO_ATTEMPT_COMPLETION","process_group_absence_alone":false,"required":["process PROVEN_DEAD","provider writer RELEASED","Executive writer released through existing owner","wait task terminal or cancelled-and-joined","monitor task terminal or cancelled-and-joined","stdout and stderr pumps terminal with closed descriptors","resource stopped and terminal artifact receipt sealed when required","capture completeness stated truthfully","dedicated-UID sweep passing"]},"unbound_formulas":{"G1_START_UNBOUND":["exact start INTENT exists","exact start provider-dispatch commitment exists","exact start EFFECT_UNKNOWN exists","exact start worker receipt exists","matching APPLIED and RECONCILED are absent"],"G2_RESUME_UNBOUND":["exact resume INTENT exists","exact resume provider-dispatch commitment exists","exact resume EFFECT_UNKNOWN exists","exact resume worker receipt exists","matching APPLIED and RECONCILED are absent"]},"unresolved_effect_unknown":{"blocks_retry_or_failover":true,"blocks_runtime_binding":true,"definition":"EFFECT_UNKNOWN with no exact later RECONCILED receipt for the same operation","deletion_or_overwrite":false},"wake_ack_separate":true,"work_admission":{"mixed_schema_or_mixed_receipt_fields":"REFUSE","normal":{"receipt_field":"tx3_applied_command_id","schema":"mastermind.orchestration_work_admission/v1","terminal_receipt_kind":"APPLIED"},"normal_path_byte_compatible":true,"reconciled":{"receipt_fields":["materialization_receipt_kind","materialization_receipt_command_id","materialization_receipt_digest"],"schema":"mastermind.orchestration_work_admission/v2","terminal_receipt_kind":"RECONCILED"}},"worker_receipt":{"atomic_create":true,"authority":"EVIDENCE_ONLY","canonical_digest":"sha256(canonical JSON of every field except receipt_digest)","fields":["schema","operation_command_id","operation_kind","attempt_id","worker_id","session_epoch_id","process_generation_id","generation_number","requested_profile_digest","provider_session_id","process_identity","observed_attestation","process_credentials","provider_home_identity","created_at","receipt_digest"],"forbidden_authority":["current generation authority","current Attempt authority","retry permission","placement authority","target assignment authority","provider-session liveness authority","completion authority"],"max_bytes":262144,"operation_kinds":["start_session","resume_session"],"overwrite":false,"path":".operator-materializations/<sha256(operation_command_id)>/receipt.json","root_owner":"control_plane.executive_worker_broker.BrokerPolicy.run_root","schema":"mastermind.operator_materialization_receipt/v1","status_owner":"control_plane.executive_worker_broker.ExecutiveWorkerBroker._ohf_materialization_status","write_owner":"control_plane.executive_worker_broker.ExecutiveWorkerBroker._ohf_start"}}
```
<!-- MAT_F0_CONTRACT_END -->

## 5. Worker receipt

The worker broker writes one immutable receipt only after the provider process/thread effect has returned and every typed observation needed by Runtime has been collected.

Path:

```text
<BrokerPolicy.run_root>/.operator-materializations/<sha256(operation_command_id)>/receipt.json
```

Rules:

1. derive the path only from the exact operation command;
2. create owner-only directories and reject symlink, owner, mode, or link-count drift;
3. exclusive-create the file with no-follow semantics; never overwrite;
4. serialize strict canonical UTF-8 JSON with duplicate-key refusal;
5. define `receipt_digest` as SHA-256 over canonical JSON of all fields except `receipt_digest`;
6. fsync the file and newly created parent directories;
7. reopen and validate before publishing process-local broker state;
8. exact replay returns the receipt with zero provider call; semantic drift conflicts;
9. receipt-only state after restart is evidence, not permission to invoke the provider again.

`created_at` is diagnostic only. Wall time has no authority.

## 6. Runtime uncertainty-resolution transaction

MAT-C1 adds two narrow methods to the existing Runtime owner:

```text
OperatorHarnessRegistry.reconcile_start_result(...)
OperatorHarnessRegistry.reconcile_resume_result(...)
```

The matching `ExecutiveOperatorHarnessPort` methods delegate one exact leased Attempt to those transactions. The orchestrator remains unchanged: on a lost or failed provider response it correctly records `EFFECT_UNKNOWN`.

On one `BEGIN IMMEDIATE` connection, each reconciliation transaction validates the same current Attempt/lease/fence/Worker/quota, original INTENT, provider-dispatch commitment, exact `EFFECT_UNKNOWN`, absent `APPLIED`, exact receipt schema/digest/profile/epoch/generation, and the current Executive-held writer. G1 must be generation 1 with an unbound epoch. G2 must be generation 2 with exact TX-10 lineage and the immutable G1 provider session.

It mutates only the existing epoch/generation/Attempt rows that ordinary TX-3/TX-11 would populate, appends exactly one `OPERATOR_OPERATION_RECONCILED` at `<operation>:reconciled`, appends no `APPLIED`, and performs no provider, broker, Slack, Wake, or filesystem call in the Runtime transaction. Matching replay is a no-op; changed replay conflicts; missing evidence quarantines the same Attempt.

## 7. Terminal receipt election

One internal Runtime validator elects materialization success:

```text
NORMAL:
  INTENT + APPLIED
  no EFFECT_UNKNOWN or RECONCILED

RECOVERED:
  INTENT + EFFECT_UNKNOWN + RECONCILED(resolution=APPLIED)
  no APPLIED
```

Everything else fails closed, including unresolved uncertainty, `RECONCILED` without uncertainty, mixed `APPLIED`, identity/digest drift, or multiple terminal candidates. `EFFECT_UNKNOWN` remains immutable after resolution.

## 8. TX-4 admission and current binding

The normal path remains byte-compatible:

```text
mastermind.orchestration_work_admission/v1
tx3_applied_command_id = <operation>:applied
```

The recovered path uses exact schema v2:

```text
mastermind.orchestration_work_admission/v2
materialization_receipt_kind       = RECONCILED
materialization_receipt_command_id = <operation>:reconciled
materialization_receipt_digest     = sha256(canonical reconciled payload)
```

The v1 and v2 key sets are exact and mutually exclusive. `seal_attestation`, active-generation validation, G1→G2 recovery validation, and `Runtime.current_harness_binding_source` consume the same terminal-election helper. `runtime_binding_projection.project_runtime_binding` remains unchanged.

## 9. G1 and G2 journeys

### G1 lost response

```text
TX-2 INTENT → dispatch → one thread/start → worker receipt
→ lost response → EFFECT_UNKNOWN → exact status read
→ reconcile_start_result → RECONCILED, never APPLIED
→ TX-4 + admission v2 → current G1 or lawful later G2
```

### G2 lost response

```text
exact G1 + TX-10 resume INTENT → dispatch → one thread/resume of G1 session
→ worker receipt → lost response → EFFECT_UNKNOWN → exact status read
→ reconcile_resume_result → RECONCILED, never APPLIED
→ TX-4 + admission v2 → recover current G2 directly
```

There is no second start, second resume, second Attempt, or G3.

## 10. Failure, teardown, and correction law

Committed dispatch plus missing receipt is `MATERIALIZATION_IDENTITY_UNKNOWN / QUARANTINE`. Malformed, partial, wrong-owner, linked, noncanonical, oversized, or digest-drifted receipts refuse. Changed operation identity conflicts. Stale lease/fence, non-CURRENT generation, uncertain liveness, or missing current writer refuses or quarantines. Process absence alone never proves remote-thread absence. No receipt authorizes retry or cross-worker/account/host failover. Corrections append immutable evidence; prior Events are never mutated.

Materialization recovery is not completion. Process-group absence while wait/monitor tasks, inherited pipes, stream pumps, or resources remain live is `CLEANUP_INCOMPLETE / NO_ATTEMPT_COMPLETION`.

## 11. No-rebuild and release boundary

MAT-C1 may modify existing Runtime and port only for the frozen reconciliation and terminal-election seams. It may not create a new session/process registry, table, migration, current-session pointer, lifecycle, aggregate, retry ledger, queue, scheduler, daemon, watcher DB, SessionTarget/RuntimeBinding store, provider broker, automatic requeue/failover, or production arming.

Stage B, Capacity, Wake/ACK, terminal return, and deployment remain separate. A protected MAT-F0 merge makes only this architecture durable and authorizes the bounded MAT-C1 implementation after fresh collision and capacity gates. It creates no runtime/provider effect and does not prove Autonomy live.
