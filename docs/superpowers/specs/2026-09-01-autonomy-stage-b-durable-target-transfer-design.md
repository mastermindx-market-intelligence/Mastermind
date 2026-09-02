# Autonomy Stage B - Durable Sol Action-Target Assignment and Transfer

**Date:** 2026-09-02  
**Owner:** Sol, AI CEO  
**Chairman:** Chris  
**Protected basis:** `Mastermind@cba0424f10ad6a9a917234c6740d92b19b018642`, Skillpack `mastermind.sol_skillpack.v1` 1.0.1  
**Operation:** `stage-b0-r1-no-duplicate-owner-freeze-v4-20260902-sol-001`  
**State:** `ARCHITECTURE_FROZEN / INITIAL_ASSIGNMENT_ONLY / SOURCE_NOT_BUILT / PRODUCTION_INERT`

## Executive ruling

The first immutable `SOL_ACTION_TARGET_ASSIGNED` Runtime Event on a CEO-owned responsibility root Job is the durable root/seat/alias assignment owner. Stage B will not create a predecessor assignment table, registry, receipt stream, mutable pointer, or policy plane.

An Event may be appended only when current protected evidence proves:

1. one exact CEO-owned responsibility root with accepted typed CEO provenance;
2. one exact CEO-owned, role-null technical carrier whose current Operator Harness Attempt is the destination Sol materialization;
3. one exact current `openai-codex` writer generation for that carrier;
4. one exact disabled Codex CEO SessionTarget; and
5. one derived, replay-safe initial-assignment command.

The root and carrier may be the same Job or different Jobs. Multiple roots may share the logical alias only when every assignment binds the same exact RuntimeBinding ID and generation. A different binding behind that alias is a conflict, never an election.

V3 correctly rejected caller overlays and fictional Wake acknowledgement fields, but its proposed predecessor root-binding owner would duplicate the assignment plane Stage B itself is meant to own. V4 supersedes V1-V3 and authorizes one bounded source wave: CEO Codex `INITIAL_ASSIGNMENT`. Succession, cross-alias transfer, ChatGPT-Sol, COO-root escalation, and production arming remain held.

## Outcome and one-system model

```text
CEO-owned responsibility root Job
+ CEO-owned role-null Codex carrier Job
+ exact current OHF Attempt / epoch / writer generation
+ canonical EXECUTIVE-CEO-CODEX-A target
+ immutable root-Job assignment Event
-> full-map SessionTarget projection
-> Event-bound current RuntimeBinding projection
-> unchanged Stage-A resolver
-> exact actor may act; stale/sister/unassigned/conflicting actor is refused
```

Executive Runtime remains the lifecycle and Event owner. SessionTarget remains the destination-definition owner. RuntimeBinding projection remains the live-writer evidence owner. Stage A remains the enforcement owner. Wake remains downstream delivery/consumption evidence. No second lifecycle, target store, binding store, authority registry, queue, or lease plane is added.

## Protected-source findings

- `root_job_bindings` is checked in empty and test-overlay-only.
- `with_root_job_bindings()` replaces the complete mapping and authenticates no assignment.
- `policy_digest()` excludes root bindings.
- no current `target_seat=ceo` plus `reasoning_surface=codex` target exists;
- `codex-app-server` is implemented;
- typed CEO-owned role-null Jobs are valid and provider identity never grants the CEO seat;
- role-null OHF materialization records current epoch/generation, observed attestation, and `OHF_LAUNCH_DECISION=ALLOW`;
- current `current_harness_binding_source()` is exact but requires roleful `ORCHESTRATION_WORK_ADMITTED` evidence;
- `runtime_binding_projection.py` owns `openai-codex -> codex`, binding ID derivation, and read-only projection;
- Stage A is storeless and requires an exact root alias, one current binding, exact surface, and exact actor binding;
- the real Wake ACK is typed `WakeAcknowledgement`, event `TARGET_ACKNOWLEDGED`, command `<wake_id>:ACK`; it cannot bootstrap initial assignment because root-scoped delivery already requires a root binding.

## Capability ledger

- `BUILT_NOT_PROVEN`: CEO Job provenance, role-null OHF materialization, Runtime Event/transaction primitives, Codex binding projection primitives, SessionTarget overlay, Codex transport, Stage A.
- `PARTIAL`: role-null CEO current-writer projection and Codex CEO target are absent.
- `SPEC_ONLY`: this V4 command/Event/fold/projection architecture.
- `NOT_BUILT`: Stage-B assignment source and action-time composition.
- `HELD`: succession, cross-alias, ChatGPT-Sol, COO-root escalation, production canary.
- `REJECTED_BY_DESIGN`: predecessor binding owner, caller overlay authority, pre-assignment ACK, caller command ID/alias choice, newest-session election, implicit generation transfer, destructive map replacement, blind retry/failover.

## Normative contract

<!-- STAGE_B_F0_CORRECTION_CONTRACT_BEGIN -->
```json
{
  "schema": "mastermind.autonomy_stage_b_f0_contract.v4",
  "protected_source_sha": "cba0424f10ad6a9a917234c6740d92b19b018642",
  "architecture_operation": "stage-b0-r1-no-duplicate-owner-freeze-v4-20260902-sol-001",
  "supersedes": ["mastermind.autonomy_stage_b_f0_contract.v1", "mastermind.autonomy_stage_b_f0_contract.v2", "mastermind.autonomy_stage_b_f0_contract.v3"],
  "current_claim": "SPEC_ONLY / SOURCE_NOT_BUILT / PRODUCTION_INERT",
  "authorized_next_wave": "STAGE-B1_CEO_CODEX_INITIAL_ASSIGNMENT_VERTICAL",
  "supported_after_source_wave": {"modes": ["INITIAL_ASSIGNMENT"], "surfaces": ["codex"]},
  "held": {"modes": ["SAME_ALIAS_GENERATION_SUCCESSION", "CROSS_ALIAS_RESPONSIBILITY_TRANSFER"], "surfaces": ["chatgpt-sol", "claude", "workspace-agent", "human"], "root_types": ["coo_owned_orchestration_root"]},
  "canonical_target": {"session_alias": "EXECUTIVE-CEO-CODEX-A", "target_seat": "ceo", "reasoning_surface": "codex", "wake_transport": "codex-app-server", "allowed_transports": ["codex-app-server"], "workstream": "executive", "target_enabled": false, "production_armed": false, "caller_selectable": false},
  "responsibility_root": {"owner": "Executive Runtime Job plus unique JOB_CREATED Event", "required": ["job_id equals root_job_id", "owner_seat equals ceo", "accepted typed CEO provenance", "status in QUEUED|RUNNING|CHECKPOINTED", "valid immutable authority policy and requested scope"], "not_required": ["root current Attempt", "Wake obligation", "Wake acknowledgement", "Slack receipt", "Agent OS attention", "provider identity"]},
  "destination_carrier": {"owner": "role-null CEO technical root Job", "required": ["carrier job_id equals carrier root_job_id", "owner_seat equals ceo", "orchestration_role is null", "accepted typed CEO provenance", "current_attempt_id equals expected target Attempt", "lease-active OPERATOR_HARNESS Attempt", "active worker provider openai-codex", "exactly one CURRENT epoch", "exactly one current unended executive-writer generation", "sealed observed attestation", "exactly one matching OHF_LAUNCH_DECISION=ALLOW"], "does_not_require": ["ORCHESTRATION_WORK_ADMITTED", "new executive seat", "new orchestration role"]},
  "assignment_owner": {"aggregate_type": "job", "aggregate_id": "responsibility root_job_id", "event_type": "SOL_ACTION_TARGET_ASSIGNED", "event_schema": "mastermind.sol_action_target_assignment/v1", "event_actor": "ceo", "first_revision": 1, "rule": "first immutable Event is the root/seat/alias owner", "alias_sharing": "same alias requires same binding_id and binding_generation", "implicit_generation_advance": false},
  "command": {"schema": "mastermind.sol_action_target_assignment_command/v1", "mode": "INITIAL_ASSIGNMENT", "fields": ["schema", "mode", "root_job_id", "expected_assignment_revision", "target_carrier_job_id", "expected_target_attempt_id", "expected_session_epoch_id", "expected_process_generation_id", "expected_session_alias", "expected_binding_id", "expected_binding_generation", "expected_target_definition_fingerprint"], "caller_may_supply_command_id": false, "expected_assignment_revision": 0, "expected_session_alias": "EXECUTIVE-CEO-CODEX-A", "derived_command_id": "SOL-TARGET-<sha256(canonical semantics)[0:32]>", "identical_replay": "return identical Event", "foreign_occupancy": "COMMAND_REPLAY_CONFLICT", "same_root_race": "one append; loser EXPECTED_REVISION_MISMATCH", "effect_unknown": "reconcile same derived id only; never retry/failover"},
  "event_required": ["schema_version", "mode", "assignment_revision", "root_job_id", "target_seat", "session_alias", "reasoning_surface", "target_definition_fingerprint", "responsibility_job_created_command_id", "responsibility_authority_fingerprint", "target_carrier_job_id", "target_carrier_job_created_command_id", "target_carrier_authority_fingerprint", "target_attempt_id", "session_epoch_id", "process_generation_id", "generation_number", "binding_id", "binding_generation", "observed_attestation_digest", "launch_decision_command_id", "command_fingerprint", "evidence_fingerprint"],
  "event_forbidden": ["native_handle", "provider_session_id", "account_label", "pid", "pgid", "process_start_identity", "boot_id", "Slack principal", "browser title", "model output", "Wake acknowledgement token"],
  "target_fingerprint": {"fields": ["session_alias", "target_seat", "reasoning_surface", "wake_transport", "allowed_transports", "workstream"], "excludes": ["root_job_bindings", "unrelated targets", "target_enabled", "production_armed", "policy_version"]},
  "runtime_extension": {"read_seam": "current_ceo_harness_binding_source", "projection_seam": "project_ceo_runtime_binding", "same_connection": true, "read_only": true, "return_types": ["ActiveOperatorBindingFacts", "RuntimeBinding"], "roleful_behavior_changed": false, "new_registry": false},
  "fold": {"root_scoped": true, "revision_start": 1, "contiguous": true, "allowed_events": ["SOL_ACTION_TARGET_ASSIGNED"], "duplicate_gap_or_branch": "ASSIGNMENT_HISTORY_CONFLICT", "unsupported_event": "UNSUPPORTED_ASSIGNMENT_MODE", "newest_event_repair": false},
  "action_time": ["reread active CEO responsibility root", "fold root assignment", "verify global alias assignments bind one RuntimeBinding", "recompute target fingerprint", "reproject current carrier binding on one Runtime connection", "require Event binding_id and binding_generation exact match", "copy complete root_job_bindings and replace selected root ceo only", "call unchanged require_sol_action_authority"],
  "transaction": ["parse and derive command id", "validate exact target definition", "BEGIN IMMEDIATE", "lookup command id before mutable reads", "read root authority and fold revision", "read carrier authority and current binding on same connection", "compare claims and global alias consistency", "append one Event", "reconcile ambiguous response only by same id"],
  "failures": ["NOT_AUTHORIZED", "ROOT_JOB_NOT_FOUND", "ROOT_JOB_NOT_ROOT", "ROOT_JOB_NOT_CEO_OWNED", "ROOT_JOB_PROVENANCE_INVALID", "ROOT_JOB_TERMINAL", "TARGET_CARRIER_NOT_FOUND", "TARGET_CARRIER_NOT_ROOT", "TARGET_CARRIER_NOT_CEO_OWNED", "TARGET_CARRIER_ROLE_CONFLICT", "TARGET_CARRIER_PROVENANCE_INVALID", "TARGET_ATTEMPT_NOT_CURRENT", "TARGET_RUNTIME_UNAVAILABLE", "TARGET_RUNTIME_CONFLICT", "TARGET_PROVIDER_UNSUPPORTED", "TARGET_CATALOG_ENTRY_MISSING", "TARGET_CATALOG_DEFINITION_CONFLICT", "TARGET_ALIAS_ALREADY_BINDS_DIFFERENT_RUNTIME", "NO_ASSIGNMENT", "ASSIGNMENT_HISTORY_CONFLICT", "EXPECTED_REVISION_MISMATCH", "COMMAND_REPLAY_CONFLICT", "STALE_ASSIGNED_BINDING", "UNSUPPORTED_ASSIGNMENT_MODE", "EFFECT_UNKNOWN_RECONCILE_FIRST", "RUNTIME_TRANSACTION_UNAVAILABLE"],
  "time_null_correction": {"timestamps": "audit only; never elect by recency", "nulls": "required evidence fails closed", "correction": "no reassignment or succession in V4; changed binding becomes unavailable", "automatic_retry": false},
  "source_paths": ["config/wake_session_targets.json", "control_plane/executive_runtime.py", "control_plane/runtime_binding_projection.py", "control_plane/sol_action_target_assignment.py", "tests/test_autonomy_stage_b_initial_assignment.py", "tests/test_autonomy_stage_b_durable_target_transfer_source_law.py"],
  "no_rebuild": {"tables": [], "migrations": [], "registries": [], "lifecycles": [], "job_attempt_worker_rows_mutated": false, "ohf_rows_mutated": false, "wake_rows_mutated": false, "provider_or_slack_calls_in_transaction": false, "stage_a_signature_changed": false, "production_armed": false},
  "source_release_claim": "BUILT_NOT_PROVEN / INITIAL_ASSIGNMENT_ONLY / PRODUCTION_DISARMED"
}
```
<!-- STAGE_B_F0_CORRECTION_CONTRACT_END -->

The JSON is normative. Prose cannot widen it.

## Critical authority laws

The responsibility root owns action scope; carrier authorities never widen it. The carrier provides materialization evidence only. The additive Runtime read seam must reuse current Job/Attempt/lease/OHF sources, revalidate unique `JOB_CREATED` CEO provenance, and accept role-null CEO carriers without weakening the existing roleful COO path.

Wake ACK is downstream. Assignment does not write Wake, provider, Slack, Job, Attempt, Worker, quota, or OHF rows. One Runtime Event is the only assignment write.

The target-definition fingerprint binds destination identity but excludes arming and unrelated catalog state. The catalog adds only disabled `EXECUTIVE-CEO-CODEX-A`; existing CEO defaults remain unchanged.

The Event binds `binding_id` and `binding_generation`. Action-time projection must reread the root, check every assignment behind the alias for one coherent binding, reproject the current carrier, and require exact Event equality. A replacement generation behind the same alias receives no authority until a separately protected succession Event exists.

`with_root_job_bindings()` replaces the complete map. Projection copies every root/seat map, changes only selected-root `ceo`, preserves sibling seats/unrelated roots, and calls the method once with the full mapping.

## Proof ceiling

Source release requires tests for exact root/carrier provenance, role-null OHF projection, unchanged roleful behavior, target definition, caller-inaccessible command ID/alias, replay, same-root concurrency, multi-root same-binding sharing, different-binding conflict, full-map preservation, exact Stage-A actor, stale-generation refusal, forbidden Event fields, and unchanged Job/Attempt/Worker/quota/OHF/Wake rows. Repository/security gates and immutable-head independent review must pass.

Green CI and merge are not production proof. A separate disposable canary must use a real Codex session, append one assignment, authorize the exact actor, refuse wrong/stale actors, prove post-assignment Wake delivery/ACK, restart, and same-command replay. Succession, cross-alias, ChatGPT-Sol, and COO-root escalation remain separate waves.

## Stop law

Stop without widening on active-writer collision, material protected-source movement, provenance-owner movement, role-null OHF evidence movement, target collision, common provider-wire change, new table/registry/lifecycle requirement, Stage-A signature change, effect uncertainty, provider action, production arming, or a seventh source path.
