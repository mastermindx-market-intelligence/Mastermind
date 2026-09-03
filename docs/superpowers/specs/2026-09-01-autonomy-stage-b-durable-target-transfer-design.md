---
schema: mastermind.autonomy_stage_b_f0_design.v6
architecture_revision: v6-alias-scoped-ceo-carrier
operation: stage-b0-r2-alias-carrier-correction-20260903-sol-001
capability: SPEC_ONLY
production_effect: NONE
---

# Autonomy Stage B — alias-scoped CEO carrier assignment

## Status

This records-only correction supersedes the protected root-claim model. The strict CEO-v2 root remains the root-level `coo` / `aggregation` responsibility aggregate and is never relabeled, cleared, or claimed as the CEO writer. Capacity C2 creates or reuses one separate alias-scoped, root-level, role-null, READ-only CEO carrier Job and commits source-root-to-carrier evidence. MAT-S1 materializes that carrier Attempt through the existing Operator Harness and MAT-F0 effect-certain semantics. Only after the exact current carrier binding exists may Stage-B1 append the first assignment on the source-root aggregate through unchanged Stage A.

Current state is `SPEC_ONLY / CORRECTION_REQUIRED / SOURCE_NOT_BUILT / PRODUCTION_INERT`. No assignment mode is authorized now. The protected Codex CEO target remains disabled and the system remains globally production-disarmed.

## One-system model

```text
CEO-v2 intent
-> root-level COO aggregation responsibility root
-> protected C1 selection
-> C2 V2 creates or reuses one alias-scoped CEO carrier and commits root-to-carrier evidence
-> MAT-S1 materializes only the carrier Attempt through existing OHF + MAT-F0 semantics
-> Stage-B1 assigns the logical office on the source-root aggregate
-> unchanged Stage-A exact-actor enforcement
```

Many responsibility roots converge on one logical `EXECUTIVE-CEO-CODEX-A` office. Executive Runtime remains the only Job, Attempt, Worker, quota, lease, fence, and Event owner. Capacity and Operator Harness retain their existing selection, claim, provider-session, epoch, generation, and writer ownership. SessionTargetRegistry owns the target definition; RuntimeBinding projection owns the current concrete binding; Stage B owns only the source-root assignment Event.

## Normative contract

<!-- STAGE_B_F0_CORRECTION_CONTRACT_BEGIN -->
```json
{
  "alias_carrier_owner": {
    "cardinality": "one initial carrier Job per session_alias and carrier_generation",
    "creation_command": "SOL-CARRIER-<sha256(canonical alias target-definition fingerprint and generation semantics)[0:32]>",
    "creation_command_schema": "mastermind.sol_session_carrier_command/v1",
    "creation_provenance_schema": "mastermind.sol_session_carrier/v1",
    "identity_excludes": [
      "source_root_job_id"
    ],
    "identity_scope": [
      "session_alias",
      "target_definition_fingerprint",
      "carrier_generation"
    ],
    "many_source_roots_may_reference_one_carrier": true,
    "one_carrier_per_source_root": false,
    "owner": "Executive Runtime existing Job Attempt Worker Event plane",
    "shape": {
      "allowed_write_paths": [],
      "attempt_limit": 1,
      "carrier_generation": 1,
      "depth": 0,
      "escalation_target": "ceo",
      "orchestration_role": null,
      "owner_seat": "ceo",
      "parent_job_id": null,
      "requested_authorities": [
        "READ"
      ],
      "root_job_id": "self",
      "validation_commands": []
    },
    "succession_supported_now": false
  },
  "architecture_operation": "stage-b0-r2-alias-carrier-correction-20260903-sol-001",
  "architecture_revision": "v6-alias-scoped-ceo-carrier",
  "capacity_c2_commitment": {
    "aggregate_id": "source responsibility root_job_id",
    "caller_may_supply_carrier_identity": false,
    "changed_payload": "COMMAND_REPLAY_CONFLICT",
    "command_schema": "mastermind.capacity_placement_commitment_command/v2",
    "event_forbidden": [
      "runtime_binding_id",
      "runtime_binding_generation",
      "provider_session_id",
      "native_handle",
      "account_label",
      "actor binding",
      "aggregation_handoff_command_id",
      "aggregation_handoff_digest",
      "plan_attempt_id",
      "plan_digest"
    ],
    "event_required": [
      "source_root_job_id",
      "source_job_created_command_id",
      "source_authority_fingerprint",
      "placement_mode",
      "session_alias",
      "target_definition_fingerprint",
      "carrier_job_id",
      "carrier_job_created_command_id",
      "carrier_authority_fingerprint",
      "carrier_generation",
      "carrier_disposition",
      "committed_carrier_attempt_id",
      "selected_worker_id",
      "selected_quota_class",
      "committed_placement_snapshot_digest",
      "commitment_command_id",
      "command_fingerprint",
      "commitment_evidence_digest"
    ],
    "event_schema": "mastermind.capacity_placement_commitment/v2",
    "event_type": "CAPACITY_PLACEMENT_COMMITTED",
    "existing_session_reuse": {
      "appends_one_root_commitment": true,
      "changes_quota_or_lease": false,
      "creates_carrier_attempt": false,
      "creates_carrier_job": false,
      "requires_exact_current_carrier_attempt_and_writer": true,
      "requires_one_exact_current_alias_carrier": true
    },
    "historical_event_is_current_authority": false,
    "identical_replay": "lookup immutable command then revalidate current source and carrier truth",
    "mode_disposition": {
      "existing_session_reuse": "reused",
      "new_session_materialization": "created"
    },
    "new_session_materialization": {
      "appends_one_root_commitment": true,
      "atomic_owner": "one existing BEGIN IMMEDIATE Runtime transaction",
      "claims_selected_worker_and_quota": true,
      "creates_carrier_attempt": true,
      "creates_carrier_job": true,
      "persists_placement_snapshot": true,
      "requires_no_existing_alias_carrier": true
    },
    "optimistic_preconditions": [
      "expected_source_root_revision"
    ],
    "owner": "CAPACITY_C2_EXISTING_EXECUTIVE_TRANSACTION_AND_CLAIM_OWNER",
    "placement_modes": [
      "new_session_materialization",
      "existing_session_reuse"
    ],
    "source_root_claimed": false,
    "stable_command_fields": [
      "source_root_job_id",
      "responsibility_ref",
      "placement_mode",
      "selection_document_digest",
      "selection_evidence_digest",
      "selected_worker_id",
      "selected_quota_class",
      "committed_placement_snapshot_digest",
      "session_alias",
      "target_definition_fingerprint",
      "carrier_generation",
      "carrier_job_created_command_id"
    ],
    "status": "MISSING_SOURCE_IMPLEMENTATION"
  },
  "current_state": {
    "authorized_modes_now": [],
    "claim": "SPEC_ONLY / CORRECTION_REQUIRED / SOURCE_NOT_BUILT / PRODUCTION_INERT",
    "production_armed": false,
    "provider_effect": false,
    "runtime_effect": false,
    "source_implementation_authorized_now": false
  },
  "failures": [
    "SOURCE_ROOT_NOT_STRICT_V2_AGGREGATION",
    "TARGET_CARRIER_MISSING",
    "TARGET_CARRIER_CARDINALITY_CONFLICT",
    "TARGET_CARRIER_PROVENANCE_INVALID",
    "TARGET_CARRIER_NOT_CEO_OWNED",
    "TARGET_CARRIER_NOT_ROLE_NULL",
    "TARGET_CARRIER_ATTEMPT_MISMATCH",
    "TARGET_CARRIER_NOT_CURRENT",
    "TARGET_CARRIER_SUCCESSION_UNSUPPORTED",
    "PLACEMENT_COMMITMENT_MISSING",
    "TARGET_RUNTIME_NOT_MATERIALIZED",
    "TARGET_ALIAS_ALREADY_BINDS_DIFFERENT_RUNTIME",
    "COMMAND_REPLAY_CONFLICT",
    "EFFECT_UNKNOWN_RECONCILE_FIRST"
  ],
  "mat_s1_writer_materialization": {
    "consumes_attempt": "committed_carrier_attempt_id",
    "effect_unknown": "quarantine unresolved identity; no retry failover replacement carrier or G3",
    "entry": "bounded role-null CEO-carrier materialization",
    "fabricates_orchestration_work_admission": false,
    "owner": "existing Operator Harness Runtime broker and Codex adapter",
    "runtime_binding_source": "exact current CEO carrier Attempt after accepted OHF materialization",
    "source_root_runtime_binding_forbidden": true,
    "status": "MISSING_SOURCE_IMPLEMENTATION",
    "uses_mat_f0_normal_and_reconciled_start_semantics": true,
    "uses_plan_only_supervisor": false
  },
  "no_rebuild": {
    "capacity_selector_or_claim_owner_duplicated": false,
    "executive_job_attempt_worker_event_owner_duplicated": false,
    "new_lifecycles": [],
    "new_migrations": [],
    "new_provider_registries": [],
    "new_queues": [],
    "new_retry_planes": [],
    "new_runtime_binding_stores": [],
    "new_schedulers": [],
    "new_tables": [],
    "new_target_registries": [],
    "operator_harness_owner_duplicated": false,
    "stage_a_owner_changed": false
  },
  "ordered_waves": [
    "STAGE_B_R2_RECORDS_CORRECTION",
    "CAPACITY_C2_V2_PURE_CONTRACT",
    "CAPACITY_C2_R1_ATOMIC_CARRIER_COMMITMENT",
    "MAT_F0_EFFECT_CERTAIN_PREREQUISITE",
    "MAT_S1_ROLE_NULL_CEO_CARRIER_MATERIALIZATION",
    "STAGE_B1_INITIAL_ASSIGNMENT",
    "LIVE_PRODUCTION_DISARMED_CANARY"
  ],
  "protected_runtime_sha": "642fa62540f0f2565ccc484a350f2cd0a2259015",
  "record_paths": [
    "docs/superpowers/specs/2026-09-01-autonomy-stage-b-durable-target-transfer-design.md",
    "docs/superpowers/plans/2026-09-01-autonomy-stage-b-durable-target-transfer.md",
    "tests/test_autonomy_stage_b_durable_target_transfer_source_law.py"
  ],
  "release_truth": {
    "green_ci_is_production_proof": false
  },
  "schema": "mastermind.autonomy_stage_b_f0_contract.v6",
  "source_responsibility_root": {
    "authority_source": "accepted mastermind.ceo_intent.v2 provenance",
    "ceo_office_assignment_requires_coo_handoff": false,
    "escalation_target": "coo",
    "forbidden": [
      "relabel root to ceo",
      "clear aggregation role",
      "claim root Attempt for CEO carrier",
      "project root Attempt as ceo RuntimeBinding",
      "caller-created root binding overlay"
    ],
    "orchestration_role": "aggregation",
    "remains_coo_responsibility_aggregate": true,
    "remains_stage_b_assignment_aggregate": true,
    "remains_unclaimed_by_capacity_c2": true,
    "root_kind": "CEO_V2_AGGREGATION_ROOT",
    "stored_owner_seat": "coo"
  },
  "stage_b1_assignment": {
    "aggregate_id": "source responsibility root_job_id",
    "caller_exposed_destination_or_carrier_fields": [],
    "command_fields": [
      "root_job_id",
      "placement_commitment_command_id",
      "expected_placement_commitment_digest",
      "expected_session_alias",
      "carrier_job_id",
      "carrier_attempt_id",
      "expected_binding_id",
      "expected_binding_generation",
      "expected_target_definition_fingerprint"
    ],
    "command_schema": "mastermind.sol_action_target_assignment_command/v2",
    "complete_map_projection": true,
    "cross_alias_transfer_supported_now": false,
    "event_schema": "mastermind.sol_action_target_assignment/v2",
    "event_type": "SOL_ACTION_TARGET_ASSIGNED",
    "first_revision": 1,
    "mode": "INITIAL_ASSIGNMENT",
    "owner": "Executive Runtime Event plane",
    "stage_a_owner": "unchanged require_sol_action_authority",
    "stage_a_signature_changed": false,
    "status": "MISSING_SOURCE_IMPLEMENTATION",
    "succession_supported_now": false
  },
  "supersedes": [
    "mastermind.autonomy_stage_b_f0_contract.v1",
    "mastermind.autonomy_stage_b_f0_contract.v2",
    "mastermind.autonomy_stage_b_f0_contract.v3",
    "mastermind.autonomy_stage_b_f0_contract.v4",
    "mastermind.autonomy_stage_b_f0_contract.v5"
  ],
  "target_definition_owner": {
    "caller_selectable": false,
    "definition": {
      "allowed_transports": [
        "codex-app-server"
      ],
      "reasoning_surface": "codex",
      "session_alias": "EXECUTIVE-CEO-CODEX-A",
      "target_enabled": false,
      "target_seat": "ceo",
      "wake_transport": "codex-app-server",
      "workstream": "executive"
    },
    "fingerprint_fields": [
      "session_alias",
      "target_seat",
      "reasoning_surface",
      "wake_transport",
      "allowed_transports",
      "workstream"
    ],
    "global_production_armed": false,
    "owner": "SessionTargetRegistry",
    "session_alias": "EXECUTIVE-CEO-CODEX-A"
  }
}
```
<!-- STAGE_B_F0_CORRECTION_CONTRACT_END -->

## Consequences

1. C2 never claims or relabels the source root. Different roots derive different commitment commands while converging on the same carrier creation identity.
2. New materialization creates and claims the first carrier; reuse requires the exact current carrier Attempt and accepted writer. The two modes and dispositions are non-interchangeable.
3. RuntimeBinding is absent from C2. MAT-S1 obtains it only from the exact carrier Attempt after accepted OHF materialization, using MAT-F0 normal or reconciled terminal evidence.
4. Stage-B1 derives every identity from current source, C2, target, carrier, and binding truth. Historical success never authenticates itself.
5. Terminal, stale, moved, ambiguous, or multiply present carrier state is unavailable. V6 has no succession, replacement, reassignment, retry, failover, implicit generation advance, or G3.

## Release boundary

A protected merge makes only this corrected source law durable. It does not implement C2, materialize a provider or RuntimeBinding, enable the target, append an assignment, dispatch Wake, deploy, or prove autonomy live.
