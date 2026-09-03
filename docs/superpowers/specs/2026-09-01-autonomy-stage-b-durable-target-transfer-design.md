---
schema: mastermind.autonomy_stage_b_f0_design.v5
architecture_revision: v5.2-claim-then-materialize-binding
operation: stage-b0-r1-real-owner-gap-repair-20260902-sol-001
capability: SPEC_ONLY
production_effect: NONE
---

# Autonomy Stage B - Trusted Initial Sol Action-Target Assignment

## Status

This records-only architecture supersedes Stage-B V1-V5.1. It freezes one narrow future capability: after an admitted CEO responsibility root has been transactionally claimed by Capacity C2 and the existing Operator Harness has separately materialized one exact current Codex writer for that committed Attempt, the existing Executive service may append the first immutable root-scoped Sol action-target assignment and expose it through the unchanged Stage-A resolver.

Current state is `SPEC_ONLY / PREDECESSORS_HELD / SOURCE_NOT_BUILT / PRODUCTION_INERT`.

V5.2 closes five prior authority/ownership/timing errors:

1. root creation is grounded in the real protected production call path, not a test overlay;
2. a caller, model, selected snapshot, provider identity or destination session cannot authorize its own assignment;
3. replay never returns an old assignment as authority without revalidating the current root, C2 commitment, target definition and binding generation;
4. the Codex CEO target definition is one separately protected SessionTargetRegistry predecessor and is consumed byte-for-byte by Stage-B1 rather than recreated on the assignment carrier;
5. Capacity C2 records the atomic Worker/Attempt claim and placement snapshot only. It cannot claim a RuntimeBinding that does not exist until a later accepted Operator Harness session/generation/provider writer has materialized.

## One-system model

```text
CeoIngress v2
-> ExecutiveControlService._submit_service_intent
-> ceo_intent.submit_intent
-> Runtime.jobs.create_v2_orchestration_root
-> admitted CEO responsibility root

protected Capacity C1 selection
-> Capacity C2 same-transaction reread and canonical Worker/Attempt claim
-> immutable root-bound CAPACITY_PLACEMENT_COMMITTED Event
   (Attempt + placement snapshot; no RuntimeBinding yet)

separately protected disabled EXECUTIVE-CEO-CODEX-A target definition

existing Operator Harness start/resume/current-writer owner
-> accepted SessionEpoch + ProcessGeneration + provider session
-> runtime_binding_projection projects exact current binding

existing ExecutiveControlService current-writer materialization/replay path
-> Stage-B initial-assignment reducer
-> immutable root-scoped SOL_ACTION_TARGET_ASSIGNED Event
-> complete-map SessionTargetRegistry projection
-> unchanged require_sol_action_authority
```

Executive Runtime remains the only Job, Attempt, Worker and Event owner. Capacity C2 owns the atomic Worker/Attempt claim commitment. Operator Harness owns provider-session materialization and accepted current writer state. SessionTargetRegistry owns logical destination definitions. RuntimeBinding projection owns current concrete materialization. Stage B owns only the root-to-logical-Sol action-target assignment Event. Stage A remains the sole action-time actor enforcement owner.

## Normative contract

<!-- STAGE_B_F0_CORRECTION_CONTRACT_BEGIN -->
```json
{
  "schema": "mastermind.autonomy_stage_b_f0_contract.v5",
  "architecture_revision": "v5.2-claim-then-materialize-binding",
  "protected_source_sha": "0d5c80bba8c69b5d1ed86aa3d32c9003a4252c73",
  "architecture_operation": "stage-b0-r1-real-owner-gap-repair-20260902-sol-001",
  "supersedes": [
    "mastermind.autonomy_stage_b_f0_contract.v1",
    "mastermind.autonomy_stage_b_f0_contract.v2",
    "mastermind.autonomy_stage_b_f0_contract.v3",
    "mastermind.autonomy_stage_b_f0_contract.v4",
    "mastermind.autonomy_stage_b_f0_contract.v5.1"
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
      "CAPACITY_C1_PROTECTED",
      "CAPACITY_C2_ROOT_BOUND_CLAIM_COMMITMENT_PROTECTED",
      "EXECUTIVE_CEO_CODEX_A_TARGET_PROTECTED",
      "EXACT_CURRENT_OHF_WRITER_MATERIALIZED"
    ]
  },
  "production_root_owner": {
    "root_kind": "CEO_V2_ORCHESTRATION_ROOT",
    "call_path": [
      "CeoIngress v2",
      "ExecutiveControlService._submit_service_intent",
      "ceo_intent.submit_intent",
      "Runtime.jobs.create_v2_orchestration_root"
    ],
    "required": [
      "job_id equals root_job_id",
      "owner_seat equals ceo",
      "orchestration_role is null",
      "accepted mastermind.ceo_intent.v2 provenance",
      "unique canonical JOB_CREATED command",
      "status in QUEUED|RUNNING|CHECKPOINTED",
      "immutable authority policy and requested scope"
    ],
    "replay_owner": "ceo_intent.submit_intent command lookup plus strict v2 root reconstruction",
    "forbidden_substitutes": [
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
    "aggregate_id": "responsibility root_job_id",
    "required": [
      "exact root_job_id",
      "selection_document_digest",
      "selection_evidence_digest",
      "selected_worker_id",
      "selected_quota_class",
      "committed_attempt_id",
      "committed_placement_snapshot_digest",
      "commitment_command_id",
      "commitment_evidence_digest",
      "canonical Worker and Attempt claim already committed"
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
      "recompute and compare the C1 selection",
      "reread capacity occupancy fence and current Worker facts",
      "claim existing canonical Worker and Attempt owners",
      "persist the canonical placement snapshot on the Attempt",
      "append one immutable root-bound claim commitment Event",
      "changed stale conflicting or effect-unknown candidate aborts",
      "do not select a second candidate inside the same modifying operation"
    ],
    "c1_selection_is_authority": false,
    "runtime_binding_alone_is_authority": false,
    "caller_destination_is_authority": false
  },
  "target_definition_owner": {
    "status": "ABSENT_PROTECTED_SOURCE",
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
    "requires_attempt_id_from_c2": true,
    "required_current_facts": [
      "committed Attempt remains canonical current Attempt for the root Job",
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
    "aggregate_id": "responsibility root_job_id",
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
    "entry": "successful or identically replayed exact current-writer materialization after C2 commitment",
    "assignment_function": "sol_action_target_assignment.assign_initial_target",
    "caller_exposed_destination_fields": [],
    "caller_may_invoke_assignment_directly": false,
    "caller_may_supply_actor_label": false,
    "caller_may_supply_actor_binding": false,
    "caller_may_supply_worker_attempt_or_runtime_binding": false,
    "authority": [
      "admitted CEO v2 root",
      "exact protected C2 root-bound claim commitment Event",
      "exact protected target definition",
      "exact current RuntimeBinding projected after OHF materialization"
    ],
    "crash_gap_behavior": "C2 commitment may remain safely unassigned while no current writer exists; exact materialization/replay re-enters the same derived assignment command",
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
      "active admitted CEO v2 root and immutable authority provenance",
      "exact root-bound C2 claim commitment Event and digest",
      "canonical current Worker and Attempt identities from the commitment",
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
      "reread active admitted CEO responsibility root",
      "fold root assignment Event",
      "reread and validate the exact C2 claim commitment",
      "require the committed Attempt remains the canonical current Attempt",
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
    "ROOT_JOB_NOT_ROOT",
    "ROOT_JOB_NOT_CEO_OWNED",
    "ROOT_JOB_PROVENANCE_INVALID",
    "ROOT_JOB_TERMINAL",
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
    "nulls": "every required root commitment target writer and binding fact fails closed when absent",
    "correction": "V5.2 has no reassignment or succession; a moved binding becomes unavailable",
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
    "capacity_commitment_owner_duplicated": false,
    "runtime_binding_owner_duplicated": false,
    "wake_owner_duplicated": false,
    "provider_or_slack_calls_in_transaction": false,
    "production_armed": false
  }
}
```
<!-- STAGE_B_F0_CORRECTION_CONTRACT_END -->

## Critical rulings

### Root authority is real and already protected

The root does not originate from `root_job_bindings`, a test fixture or an arbitrary in-process `Job`. The accepted production path is the existing CeoIngress-to-Executive-service-to-`ceo_intent.submit_intent` chain ending in `create_v2_orchestration_root`. The immutable v2 root and its canonical `JOB_CREATED` command are the responsibility owner.

### C1 selects; C2 atomically claims; OHF materializes; Stage B assigns

C1 remains deterministic evidence and explicitly not commitment. C2 performs the modifying reread and canonical Worker/Attempt claim through the existing Executive transaction owner, persists the existing placement snapshot on the Attempt, and appends one root-bound claim commitment Event.

C2 does not and cannot commit a RuntimeBinding. At claim time the Operator Harness SessionEpoch, ProcessGeneration and provider session may not exist. The existing Operator Harness later materializes the exact current writer under its own effect/reconciliation law. RuntimeBinding projection then derives the current binding from that accepted writer.

Stage B may assign only after both the C2 commitment and exact current-writer projection exist. It starts no provider work and creates no materialization lifecycle.

### Target definition is one separate predecessor

SessionTargetRegistry owns the exact disabled `EXECUTIVE-CEO-CODEX-A` definition. That definition must be protected by its own bounded owner carrier before Stage-B1 starts. Stage-B1 reads and fingerprints the protected entry; it does not modify `config/wake_session_targets.json`, recreate the target or combine target-definition review with assignment implementation.

### Initial assignment is a system transition, not destination self-authorization

The destination session does not assign itself. The internal Executive service current-writer materialization/replay path invokes Stage B only after it can revalidate the C2 commitment and project the exact binding. No public request may carry a worker, Attempt, carrier Job, RuntimeBinding, native handle, actor label or destination alias that selects the target. The command contains only comparisons to already-owned facts.

### Replay is current-truth reconciliation

A command-id hit is not automatic success. Replaying the same logical operation revalidates the root, C2 claim commitment, canonical claimed rows, target definition and current writer/binding generation. A replaced generation is unavailable until a separately protected succession architecture exists. Historical success cannot authorize a stale session.

### Stage A remains unchanged

Stage B folds the immutable assignment into a complete SessionTargetRegistry overlay, then calls the existing `require_sol_action_authority`. The current actor must still match the exact RuntimeBinding identity. Assignment never turns the Event or a receipt into a reusable action token.

## Capability ledger

- `BUILT_NOT_PROVEN`: CEO v2 root admission/replay, Executive Runtime Event/transaction primitives, Worker/Attempt claim, Operator Harness current-writer owner, RuntimeBinding projection, SessionTarget overlay, Stage A and Codex wake transport.
- `SPEC_ONLY`: this V5.2 Stage-B architecture.
- `NOT_BUILT`: Capacity C2 claim commitment Event, disabled Codex CEO target, Stage-B assignment source and service composition.
- `HELD`: implementation until C1, C2 and target predecessors protect and one exact current writer materializes; succession, cross-alias transfer, ChatGPT-Sol, COO-root escalation and production canary.
- `REJECTED_BY_DESIGN`: caller/destination self-assignment, C1-as-commitment, RuntimeBinding-as-C2-claim, arbitrary root overlays, direct public assignment call, newest-session election, implicit generation transfer, destructive map replacement, duplicate target ownership and blind retry/failover.

## Stop law

Stop without widening on an active path collision, material movement of the CEO root/C2/Event/OHF/RuntimeBinding/Stage-A owners, a need for a new table/registry/lifecycle/queue/lease, common provider-wire change, Stage-A signature change, target-config modification inside Stage-B1, effect uncertainty, provider action, production arming or a seventh Stage-B1 source path.