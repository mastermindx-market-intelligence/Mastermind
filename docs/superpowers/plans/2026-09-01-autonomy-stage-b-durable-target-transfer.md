---
schema: mastermind.autonomy_stage_b_f0_plan.v5
architecture_revision: v5.3-post-handoff-aggregation
operation: stage-b0-r1-real-owner-gap-repair-20260902-sol-001
capability: SPEC_ONLY
production_effect: NONE
---

# Stage-B0 v5.3 — post-handoff aggregation implementation plan

## Outcome

Freeze the shortest correct path from an accepted CEO-v2 responsibility to one exact Codex CEO action target without inventing a parallel lifecycle:

```text
CEO-v2 intent
-> strict aggregation root
-> canonical COO planner/work/review-repair lifecycle
-> validated aggregation handoff
-> C1 deterministic selection
-> C2 atomic aggregation-root claim commitment
-> existing Operator Harness materializes the exact current writer
-> Stage-B1 immutable initial target assignment
-> unchanged Stage-A exact-actor enforcement
```

The protected Runtime is authoritative. `create_v2_orchestration_root()` creates an aggregation root with the canonical stored owner seat `coo`; admission alone is not claim readiness. C2 cannot run until the existing COO cycle has produced the exact validated aggregation handoff.

## Current source state

- records only;
- no currently authorized assignment mode;
- no Runtime, Worker, Attempt, provider, target, Wake, deployment or production effect;
- source implementation held on explicit predecessors;
- Capacity C1 remains selection evidence only;
- the disabled Codex CEO target remains a separate source prerequisite;
- exact current Operator Harness materialization remains a runtime prerequisite.

## Correction gate

<!-- STAGE_B1_CORRECTION_GATE_BEGIN -->
```json
{
  "schema": "mastermind.autonomy_stage_b1_correction_gate.v5",
  "architecture_revision": "v5.3-post-handoff-aggregation",
  "protected_runtime_sha": "c7fa5b43de6ca702f942fbf20cbe3ac45a02b0f6",
  "records_paths": [
    "docs/superpowers/specs/2026-09-01-autonomy-stage-b-durable-target-transfer-design.md",
    "docs/superpowers/plans/2026-09-01-autonomy-stage-b-durable-target-transfer.md",
    "tests/test_autonomy_stage_b_durable_target_transfer_source_law.py"
  ],
  "records_only": true,
  "architecture_state": "FROZEN",
  "stage_b1_state": "HELD_PREDECESSORS",
  "predecessors": [
    "COO_AGGREGATION_HANDOFF_VALIDATED",
    "CAPACITY_C1_PROTECTED",
    "CAPACITY_C2_ROOT_BOUND_CLAIM_COMMITMENT_PROTECTED",
    "EXECUTIVE_CEO_CODEX_A_TARGET_PROTECTED",
    "EXACT_CURRENT_OHF_WRITER_MATERIALIZED"
  ],
  "next_program_wave": "CAPACITY_C2_POST_HANDOFF_AGGREGATION_CLAIM_VERTICAL",
  "stage_b1_after_predecessors": "STAGE_B1_CEO_CODEX_INITIAL_ASSIGNMENT_VERTICAL",
  "production_assignment_caller": "ExecutiveControlService exact current-writer materialization/replay path after post-handoff C2 commitment",
  "c2_root_role": "aggregation",
  "c2_root_stored_owner_seat": "coo",
  "c2_requires_validated_aggregation_handoff": true,
  "c2_pre_handoff_mutation_allowed": false,
  "c2_contains_runtime_binding": false,
  "destination_session_self_authority": false,
  "caller_destination_authority": false,
  "trusted_replay_revalidates_current_truth": true,
  "requires_exact_binding_generation_fence": true,
  "requires_complete_root_map_preservation": true,
  "requires_unchanged_stage_a": true,
  "runtime_effect": false,
  "provider_effect": false,
  "production_armed": false
}
```
<!-- STAGE_B1_CORRECTION_GATE_END -->

## Ordered completion sequence

1. PROTECT_STAGE_B0_V5_3_POST_HANDOFF_ARCHITECTURE
2. PROTECT_CAPACITY_C1_SELECTION
3. COMPLETE_COO_CYCLE_TO_VALIDATED_AGGREGATION_HANDOFF
4. BUILD_CAPACITY_C2_POST_HANDOFF_AGGREGATION_CLAIM_COMMITMENT
5. ADD_DISABLED_EXECUTIVE_CEO_CODEX_A_TARGET
6. MATERIALIZE_EXACT_CURRENT_OHF_WRITER
7. RED_STAGE_B1_PRODUCTION_ROOT_COMMITMENT_AND_BINDING_CHAIN
8. BUILD_STAGE_B1_INITIAL_ASSIGNMENT
9. RUN_SEPARATE_DISPOSABLE_CANARY

Steps 2 and 5 may protect in parallel. Runtime execution remains ordered: the COO handoff must exist before C2; C2 must exist before materialization is accepted for Stage B; the exact current writer and disabled target definition must both exist before assignment.

## Wave C2 — atomic post-handoff aggregation claim

### Mission

```text
strict CEO-v2 aggregation root
+ exact current validated aggregation handoff
+ exact protected C1 document
-> one existing BEGIN IMMEDIATE claim transaction
-> aggregation Worker/Attempt claim + placement snapshot
-> CAPACITY_PLACEMENT_COMMITTED
```

### Exact owner extension

Extend the existing `AttemptRegistry.claim_job` transaction through one private, unforgeable C2 capability. Do not call public `claim_job()` and append a commitment in a second transaction. Do not copy the quota CAS, fence, Attempt insert, Job transition or placement-snapshot SQL.

Before any capacity mutation, the C2 path must:

1. reconstruct the strict CEO-v2 aggregation root and accepted immutable provenance;
2. prove `orchestration_role == "aggregation"` and stored `owner_seat == "coo"`;
3. require root `QUEUED`, no current Attempt and no cancel request;
4. call the existing `_validated_aggregation_handoff()` inside the same transaction;
5. bind the exact handoff command/digest, plan Attempt and plan digest;
6. validate/recompute C1 exactly once;
7. force the exact selected Worker/quota/provider candidate;
8. reuse the existing claim mutation;
9. append one root-bound commitment Event before commit.

A new root with no planner, an unadmitted plan, any living work/review/repair child, or a missing/changed handoff produces zero mutation. C2 never changes planner creation, plan admission, review/repair policy or child dispatch.

### Maximum six paths

- `control_plane/executive_placement_commitment.py`
- `control_plane/executive_runtime.py`
- `control_plane/executive_service.py` only if a real internal consumer is required
- `tests/test_executive_placement_commitment.py`
- the current canonical Executive Runtime test owner
- optionally the current canonical Executive service test owner

No seventh path. No table, migration, capacity registry, queue, scheduler, lease, target, RuntimeBinding or provider path.

### Required proof

- exact post-handoff claim succeeds once;
- every pre-handoff state is zero mutation;
- C1, handoff, root revision, Worker/quota/fence and placement snapshot are exact;
- injected failure before commitment Event rolls back Job/Attempt/quota/Event together;
- identical replay revalidates current root, handoff, C1, Attempt and snapshot;
- changed replay conflicts;
- same-root concurrency yields one Event;
- independent roots remain independent;
- no RuntimeBinding/provider/Wake/assignment effect.

## Wave Stage-B1 — initial target assignment

### Mission

```text
post-handoff aggregation root
+ exact protected C2 commitment for its current aggregation Attempt
+ exact disabled EXECUTIVE-CEO-CODEX-A definition
+ exact current RuntimeBinding projected after OHF materialization
-> SOL_ACTION_TARGET_ASSIGNED revision 1
-> complete-map SessionTargetRegistry projection
-> unchanged require_sol_action_authority
```

### Maximum six paths

- `control_plane/executive_runtime.py`
- `control_plane/runtime_binding_projection.py`
- `control_plane/sol_action_target_assignment.py`
- `control_plane/executive_service.py`
- `tests/test_autonomy_stage_b_initial_assignment.py`
- `tests/test_autonomy_stage_b_durable_target_transfer_source_law.py`

No seventh path. Do not modify `config/wake_session_targets.json`. Do not modify `control_plane/sol_action_target.py`.

### Authority and replay

The internal Executive service derives the command from the root, C2 commitment, protected target definition and exact current RuntimeBinding. Public callers expose no destination fields and cannot supply actor, Worker, Attempt, RuntimeBinding, provider, account, session or command identity.

A command hit must revalidate:

- active post-handoff aggregation root;
- the same handoff bound by C2;
- exact C2 Event and canonical current aggregation Attempt;
- exact target-definition fingerprint;
- exact current RuntimeBinding ID/generation and Codex reasoning surface;
- global same-alias coherence.

A moved handoff, commitment, Attempt or RuntimeBinding invalidates historical success. No current writer is `TARGET_RUNTIME_NOT_MATERIALIZED`. Effect uncertainty is reconciliation-only. No worker/provider/alias/carrier failover.

### Projection and Stage A

Fold one contiguous assignment history starting at revision 1. Copy the complete root/seat map and replace only the selected root's `ceo` alias. Call the unchanged Stage-A resolver with the actual actor RuntimeBinding. Wrong, sister, stale and replacement-generation actors remain observer-only or refused.

## Failure families

- invalid or terminal aggregation root;
- root not ready for aggregation claim;
- aggregation handoff missing or conflicting;
- placement commitment missing/conflicting/effect unknown;
- target definition missing/conflicting;
- target runtime not materialized/unavailable/conflicting;
- alias already binds another RuntimeBinding;
- assignment history conflict;
- expected revision mismatch;
- command replay conflict;
- stale assigned binding;
- effect unknown reconcile first;
- Runtime transaction unavailable.

Every refusal is fixed and value-free. Timestamps are audit only and never elect a destination.

## No-rebuild boundary

Do not add a table, migration, lifecycle, queue, scheduler, target store, RuntimeBinding store, retry ledger, watcher database or provider path. Do not duplicate the COO cycle, aggregation handoff, Capacity selector, Worker/Attempt claim, RuntimeBinding projection, Wake or Stage-A owners.

## Release boundary

This carrier is records-only. A protected merge authorizes neither C2 nor Stage-B1 implementation by itself and creates no runtime or production effect. Each later source wave stops at a current-base Draft/HOLD candidate. Provider materialization and the disposable live canary remain separate effects.
