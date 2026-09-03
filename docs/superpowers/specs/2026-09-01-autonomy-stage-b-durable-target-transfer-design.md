---
schema: mastermind.autonomy_stage_b_f0_design.v5
architecture_revision: v5.3-post-handoff-aggregation
operation: stage-b0-r1-real-owner-gap-repair-20260902-sol-001
capability: SPEC_ONLY
production_effect: NONE
---

# Autonomy Stage B — post-handoff aggregation assignment

## Status

This records-only correction supersedes Stage-B V1 through V5.2. It freezes one narrow future capability: after a strict CEO-v2 aggregation root has completed its canonical COO planner/work/review-repair lifecycle, produced one validated aggregation handoff, and then been transactionally claimed by Capacity C2, the existing Operator Harness may materialize one exact current Codex writer for that aggregation Attempt. The existing Executive service may then append the first immutable root-scoped Sol target assignment and expose it through unchanged Stage-A enforcement.

Current state is `SPEC_ONLY / PREDECESSORS_HELD / SOURCE_NOT_BUILT / PRODUCTION_INERT`.

The correction is deliberately narrow. It preserves V5.2's claim/materialization split and closes one false Runtime model: protected `create_v2_orchestration_root()` creates an `aggregation` root whose stored owner seat is `coo`; that root must remain unclaimed while the COO cycle runs and may be claimed only after the existing validated aggregation handoff.

## One-system model

```text
CeoIngress v2
-> ExecutiveControlService._submit_service_intent
-> ceo_intent.submit_intent
-> Runtime.jobs.create_v2_orchestration_root
-> strict CEO-v2 aggregation root (stored owner seat: coo)

existing COO cycle
-> create_cycle_planner
-> admit_cycle_plan
-> work / review / repair as required
-> COO_AGGREGATION_HANDOFF_READY
-> _validated_aggregation_handoff

protected Capacity C1 selection for aggregation execution
-> Capacity C2 same-transaction handoff revalidation + canonical root claim
-> immutable root-bound CAPACITY_PLACEMENT_COMMITTED Event
   (aggregation Attempt + placement snapshot; no RuntimeBinding yet)

separately protected disabled EXECUTIVE-CEO-CODEX-A target definition

existing Operator Harness start/resume/current-writer owner
-> accepted SessionEpoch + ProcessGeneration + provider session
-> runtime_binding_projection projects exact current binding

existing ExecutiveControlService current-writer materialization/replay path
-> Stage-B1 initial-assignment reducer
-> immutable root-scoped SOL_ACTION_TARGET_ASSIGNED Event
-> complete-map SessionTargetRegistry projection
-> unchanged require_sol_action_authority
```

Executive Runtime remains the only Job, Attempt, Worker, quota, lease, fence and Event owner. The COO cycle remains the only planner/work/review/repair and aggregation-handoff owner. Capacity C2 owns only the atomic post-handoff aggregation claim commitment. Operator Harness owns provider-session materialization and accepted current-writer state. SessionTargetRegistry owns logical destination definitions. RuntimeBinding projection owns current concrete materialization. Stage B owns only the root-to-logical-Sol assignment Event. Stage A remains the sole action-time actor enforcement owner.

## Normative contract

<!-- STAGE_B_F0_CORRECTION_CONTRACT_BEGIN -->
```json
{
  "schema": "mastermind.autonomy_stage_b_f0_contract.v5",
  "architecture_revision": "v5.3-post-handoff-aggregation",
  "protected_runtime_sha": "c7fa5b43de6ca702f942fbf20cbe3ac45a02b0f6",
  "architecture_operation": "stage-b0-r1-real-owner-gap-repair-20260902-sol-001",
  "supersedes": [
    "mastermind.autonomy_stage_b_f0_contract.v1",
    "mastermind.autonomy_stage_b_f0_contract.v2",
    "mastermind.autonomy_stage_b_f0_contract.v3",
    "mastermind.autonomy_stage_b_f0_contract.v4",
    "mastermind.autonomy_stage_b_f0_contract.v5.1",
    "mastermind.autonomy_stage_b_f0_contract.v5.2"
  ],
  "current_state": {
    "claim": "SPEC_ONLY / PREDECESSORS_HELD / SOURCE_NOT_BUILT / PRODUCTION_INERT",
    "authorized_modes_now": [],
    "source_implementation_authorized_now": false,
    "production_armed": false,
    "runtime_effect": false,
    "provider_effect": false
  },
  "future_supported_mode": {
    "mode": "INITIAL_ASSIGNMENT",
    "seat": "ceo",
    "reasoning_surface": "codex",
    "held_until": [
      "COO_AGGREGATION_HANDOFF_VALIDATED",
      "CAPACITY_C1_PROTECTED",
      "CAPACITY_C2_ROOT_BOUND_CLAIM_COMMITMENT_PROTECTED",
      "EXECUTIVE_CEO_CODEX_A_TARGET_PROTECTED",
      "EXACT_CURRENT_OHF_WRITER_MATERIALIZED"
    ]
  },
  "production_root_owner": {
    "root_kind": "CEO_V2_AGGREGATION_ROOT",
    "stored_owner_seat": "coo",
    "orchestration_role": "aggregation",
    "authority_source": "accepted mastermind.ceo_intent.v2 provenance",
    "call_path": [
      "CeoIngress v2",
      "ExecutiveControlService._submit_service_intent",
      "ceo_intent.submit_intent",
      "Runtime.jobs.create_v2_orchestration_root"
    ],
    "pre_claim_lifecycle": [
      "Runtime.jobs.create_cycle_planner",
      "Runtime.jobs.admit_cycle_plan",
      "canonical work review and repair children",
      "COO_AGGREGATION_HANDOFF_READY",
      "Runtime._validated_aggregation_handoff"
    ],
    "claim_readiness": [
      "job_id equals root_job_id",
      "parent_job_id is null",
      "stored owner_seat equals coo",
      "orchestration_role equals aggregation",
      "accepted mastermind.ceo_intent.v2 provenance",
      "unique canonical JOB_CREATED command",
      "root status equals QUEUED",
      "current_attempt_id is null",
      "cancel_requested_at is null",
      "all planner work review and repair children are terminal",
      "one exact validated aggregation handoff is current"
    ],
    "replay_owner": "ceo_intent.submit_intent command lookup plus strict v2 aggregation-root reconstruction",
    "forbidden_substitutes": [
      "pre-handoff root claim",
      "root_job_bindings overlay",
      "Slack message",
      "model output",
      "provider identity",
      "account label",
      "browser title",
      "caller-created Job"
    ]
  },
  "placement_commitment_owner": {
    "status": "MISSING_PREDECESSOR",
    "owner": "CAPACITY_C2_EXISTING_EXECUTIVE_TRANSACTION_AND_CLAIM_OWNER",
    "event_type": "CAPACITY_PLACEMENT_COMMITTED",
    "event_schema": "mastermind.capacity_placement_commitment/v1",
    "aggregate_type": "job",
    "aggregate_id": "aggregation root_job_id",
    "required": [
      "exact root_job_id",
      "exact aggregation_handoff_command_id",
      "exact aggregation_handoff_digest",
      "exact plan_attempt_id",
      "exact plan_digest",
      "selection_document_digest",
      "selection_evidence_digest",
      "selected_worker_id",
      "selected_quota_class",
      "committed_attempt_id",
      "committed_placement_snapshot_digest",
      "commitment_command_id",
      "commitment_evidence_digest",
      "canonical aggregation Worker and Attempt claim already committed"
    ],
    "forbidden": [
      "committed_runtime_binding_id",
      "committed_runtime_binding_generation",
      "provider_session_id",
      "native_handle",
      "account_label",
      "model output",
      "caller actor label"
    ],
    "binding_timing": "RUNTIME_BINDING_DOES_NOT_EXIST_UNTIL_OHF_WRITER_MATERIALIZATION",
    "transaction_law": [
      "BEGIN IMMEDIATE in existing Executive Runtime",
      "revalidate exact current aggregation handoff before capacity mutation",
      "recompute and compare the C1 selection",
      "reread capacity occupancy fence and current Worker facts",
      "claim existing canonical aggregation Worker and Attempt owners",
      "persist the canonical placement snapshot on the aggregation Attempt",
      "append one immutable root-bound claim commitment Event",
      "rollback Job Attempt quota and Event together on any failure",
      "changed stale conflicting or effect-unknown handoff or candidate aborts",
      "do not select a second candidate inside the same modifying operation"
    ],
    "pre_handoff_mutation_allowed": false,
    "c1_selection_is_authority": false,
    "runtime_binding_alone_is_authority": false,
    "caller_destination_is_authority": false
  },
  "target_definition_owner": {
    "status": "SEPARATE_DISABLED_SOURCE_PREREQUISITE",
    "owner": "SessionTargetRegistry",
    "required_definition": {
      "session_alias": "EXECUTIVE-CEO-CODEX-A",
      "target_seat": "ceo",
      "reasoning_surface": "codex",
      "wake_transport": "codex-app-server",
      "allowed_transports": [
        "codex-app-server"
      ],
      "workstream": "executive",
      "target_enabled": false,
      "production_armed": false,
      "caller_selectable": false
    },
    "definition_fingerprint_fields": [
      "session_alias",
      "target_seat",
      "reasoning_surface",
      "wake_transport",
      "allowed_transports",
      "workstream"
    ],
    "fingerprint_excludes": [
      "root_job_bindings",
      "unrelated targets",
      "target_enabled",
      "production_armed",
      "policy_version"
    ]
  },
  "writer_materialization_owner": {
    "owner": "EXISTING_OPERATOR_HARNESS_AND_RUNTIME_BINDING_PROJECTION",
    "starts_provider_work": false,
    "consumes_existing_current_writer_only": true,
    "requires_aggregation_attempt_id_from_c2": true,
    "required_current_facts": [
      "committed aggregation Attempt remains canonical current Attempt for the root Job",
      "accepted Operator Harness SessionEpoch",
      "accepted current ProcessGeneration",
      "exact provider session owned by that generation",
      "current writer fence",
      "provider maps to codex reasoning surface",
      "target seat and reasoning surface match"
    ],
    "not_ready": "TARGET_RUNTIME_NOT_MATERIALIZED",
    "effect_unknown": "EFFECT_UNKNOWN_RECONCILE_FIRST"
  },
  "assignment_owner": {
    "owner": "Executive Runtime Event plane",
    "aggregate_type": "job",
    "aggregate_id": "aggregation root_job_id",
    "event_type": "SOL_ACTION_TARGET_ASSIGNED",
    "event_schema": "mastermind.sol_action_target_assignment/v1",
    "first_revision": 1,
    "rule": "first immutable Event is the sole root-seat-alias assignment owner",
    "event_actor": "ceo",
    "event_actor_is_authority": false,
    "separate_assignment_table": false,
    "implicit_generation_advance": false
  },
  "production_call_path": {
    "owner": "ExecutiveControlService",
    "entry": "successful or identically replayed exact current-writer materialization after post-handoff C2 commitment",
    "assignment_function": "sol_action_target_assignment.assign_initial_target",
    "caller_exposed_destination_fields": [],
    "caller_may_invoke_assignment_directly": false,
    "caller_may_supply_actor_label": false,
    "caller_may_supply_actor_binding": false,
    "caller_may_supply_worker_attempt_or_runtime_binding": false,
    "authority": [
      "accepted post-handoff CEO v2 aggregation root",
      "exact validated aggregation handoff bound by C2",
      "exact protected C2 root-bound claim commitment Event",
      "exact protected target definition",
      "exact current RuntimeBinding projected after OHF materialization"
    ],
    "crash_gap_behavior": "C2 commitment may remain safely unassigned while no current writer exists; exact materialization or replay re-enters the same derived assignment command",
    "new_daemon_or_scheduler": false
  },
  "command": {
    "schema": "mastermind.sol_action_target_assignment_command/v1",
    "mode": "INITIAL_ASSIGNMENT",
    "fields": [
      "schema",
      "mode",
      "root_job_id",
      "expected_assignment_revision",
      "placement_commitment_command_id",
      "expected_placement_commitment_digest",
      "expected_session_alias",
      "expected_binding_id",
      "expected_binding_generation",
      "expected_target_definition_fingerprint"
    ],
    "caller_may_supply_command_id": false,
    "caller_may_supply_target_carrier_job_id": false,
    "caller_may_supply_worker_id": false,
    "caller_may_supply_attempt_id": false,
    "caller_may_supply_runtime_binding": false,
    "caller_may_supply_provider_account_or_native_handle": false,
    "expected_assignment_revision": 0,
    "expected_session_alias": "EXECUTIVE-CEO-CODEX-A",
    "derived_command_id": "SOL-TARGET-<sha256(canonical command semantics)[0:32]>",
    "identical_replay": "revalidate current truth then return the identical Event",
    "changed_payload": "COMMAND_REPLAY_CONFLICT",
    "same_root_race": "one append; loser EXPECTED_REVISION_MISMATCH",
    "effect_unknown": "reconcile only by the same derived command id; no retry or failover"
  },
  "trusted_replay": {
    "lookup_order": "derived assignment command id before mutable reads",
    "must_revalidate": [
      "canonical existing assignment Event shape and command fingerprint",
      "active post-handoff CEO v2 aggregation root and immutable authority provenance",
      "exact aggregation handoff identity bound by the C2 commitment",
      "exact root-bound C2 claim commitment Event and digest",
      "canonical current aggregation Worker and Attempt identities from the commitment",
      "exact target definition fingerprint",
      "current RuntimeBinding id generation and reasoning surface projected from the committed Attempt",
      "global same-alias assignments bind one identical RuntimeBinding"
    ],
    "stale_or_moved_binding": "STALE_ASSIGNED_BINDING",
    "foreign_commitment": "PLACEMENT_COMMITMENT_CONFLICT",
    "historical_success_is_reusable_authority": false
  },
  "event_required": [
    "schema_version",
    "mode",
    "assignment_revision",
    "root_job_id",
    "target_seat",
    "session_alias",
    "reasoning_surface",
    "target_definition_fingerprint",
    "responsibility_job_created_command_id",
    "responsibility_authority_fingerprint",
    "placement_commitment_command_id",
    "placement_commitment_digest",
    "binding_id",
    "binding_generation",
    "command_fingerprint",
    "evidence_fingerprint"
  ],
  "event_forbidden": [
    "native_handle",
    "provider_session_id",
    "account_label",
    "pid",
    "pgid",
    "process_start_identity",
    "boot_id",
    "Slack principal",
    "browser title",
    "model output",
    "caller actor label",
    "Wake acknowledgement token"
  ],
  "projection_and_stage_a": {
    "fold": "one contiguous root-scoped SOL_ACTION_TARGET_ASSIGNED revision starting at 1",
    "duplicate_gap_or_branch": "ASSIGNMENT_HISTORY_CONFLICT",
    "unsupported_event": "UNSUPPORTED_ASSIGNMENT_MODE",
    "action_time": [
      "reread active post-handoff CEO v2 aggregation root",
      "fold root assignment Event",
      "reread and validate the exact C2 claim commitment and bound aggregation handoff",
      "require the committed aggregation Attempt remains the canonical current Attempt",
      "recompute target definition fingerprint",
      "project current RuntimeBinding from the committed Attempt after OHF materialization",
      "require Event binding_id and binding_generation exact match",
      "verify every root behind the alias binds one identical RuntimeBinding",
      "copy complete root_job_bindings and replace only selected root ceo",
      "call unchanged require_sol_action_authority with the actual actor RuntimeBinding"
    ],
    "stage_a_signature_changed": false,
    "stage_a_actor_rule": "only exact RuntimeBinding identity is action-authoritative; all others are observer-only or refused"
  },
  "failures": [
    "NOT_AUTHORIZED",
    "ROOT_JOB_NOT_FOUND",
    "ROOT_JOB_NOT_AGGREGATION_ROOT",
    "ROOT_JOB_PROVENANCE_INVALID",
    "ROOT_JOB_TERMINAL",
    "ROOT_NOT_READY_FOR_AGGREGATION_CLAIM",
    "AGGREGATION_HANDOFF_MISSING",
    "AGGREGATION_HANDOFF_CONFLICT",
    "PLACEMENT_COMMITMENT_MISSING",
    "PLACEMENT_COMMITMENT_CONFLICT",
    "PLACEMENT_COMMITMENT_EFFECT_UNKNOWN",
    "TARGET_CATALOG_ENTRY_MISSING",
    "TARGET_CATALOG_DEFINITION_CONFLICT",
    "TARGET_RUNTIME_NOT_MATERIALIZED",
    "TARGET_RUNTIME_UNAVAILABLE",
    "TARGET_RUNTIME_CONFLICT",
    "TARGET_ALIAS_ALREADY_BINDS_DIFFERENT_RUNTIME",
    "NO_ASSIGNMENT",
    "ASSIGNMENT_HISTORY_CONFLICT",
    "EXPECTED_REVISION_MISMATCH",
    "COMMAND_REPLAY_CONFLICT",
    "STALE_ASSIGNED_BINDING",
    "UNSUPPORTED_ASSIGNMENT_MODE",
    "EFFECT_UNKNOWN_RECONCILE_FIRST",
    "RUNTIME_TRANSACTION_UNAVAILABLE"
  ],
  "time_null_correction": {
    "timestamps": "audit only; never elect a destination by recency",
    "nulls": "every required root handoff commitment target writer and binding fact fails closed when absent",
    "correction": "V5.3 has no reassignment or succession; a moved handoff commitment or binding becomes unavailable",
    "automatic_retry": false
  },
  "source_wave": {
    "status": "HELD_PREDECESSORS",
    "name": "STAGE_B1_CEO_CODEX_INITIAL_ASSIGNMENT_VERTICAL",
    "paths": [
      "control_plane/executive_runtime.py",
      "control_plane/runtime_binding_projection.py",
      "control_plane/sol_action_target_assignment.py",
      "control_plane/executive_service.py",
      "tests/test_autonomy_stage_b_initial_assignment.py",
      "tests/test_autonomy_stage_b_durable_target_transfer_source_law.py"
    ],
    "maximum_paths": 6,
    "target_definition_is_separate_predecessor": true,
    "release_claim": "BUILT_NOT_PROVEN / INITIAL_ASSIGNMENT_ONLY / PRODUCTION_DISARMED"
  },
  "no_rebuild": {
    "tables": [],
    "migrations": [],
    "registries": [],
    "lifecycles": [],
    "queues": [],
    "leases": [],
    "job_attempt_worker_owners_duplicated": false,
    "coo_cycle_or_handoff_owner_duplicated": false,
    "capacity_commitment_owner_duplicated": false,
    "runtime_binding_owner_duplicated": false,
    "wake_owner_duplicated": false,
    "provider_or_slack_calls_in_transaction": false,
    "production_armed": false
  }
}
```
<!-- STAGE_B_F0_CORRECTION_CONTRACT_END -->

## Consequences

1. Admission is not placement readiness. The root must remain available to the canonical COO cycle until its aggregation handoff is valid.
2. Capacity C1 remains inert evidence. C2 revalidates both the handoff and C1 inside the existing claim transaction.
3. The committed Attempt is the aggregation root Attempt. Child work/review Attempts do not become the Stage-B CEO target.
4. RuntimeBinding remains later materialization evidence and cannot substitute for the C2 commitment.
5. A caller, model, provider/account label, Slack sender or target alias cannot self-authorize assignment.
6. Identical replay is historical lookup plus complete current-truth revalidation, never historical success as standing authority.

## Release boundary

A protected merge makes only this corrected source law durable. It does not build C2, add or enable a target, start a provider, claim a root, append an assignment, dispatch Wake, deploy, or prove autonomy live.
