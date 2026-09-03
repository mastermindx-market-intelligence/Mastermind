---
schema: mastermind.autonomy_stage_b1_plan.v5
architecture_revision: v5.2-claim-then-materialize-binding
operation: stage-b0-r1-real-owner-gap-repair-20260902-sol-001
capability: SPEC_ONLY
production_effect: NONE
---

# Stage-B0-R1 V5.2 - Claim, Materialize, Then Assign

## Mission

Freeze the exact predecessor and implementation sequence for the first CEO Codex action-target assignment without creating a destination-selection or assignment authority beside Executive Runtime, Capacity C2, Operator Harness, SessionTargetRegistry, RuntimeBinding or Stage A.

The key timing law is explicit: the Capacity C2 transaction can atomically claim the Worker and Attempt and persist their placement snapshot, but the RuntimeBinding is projected only after the existing Operator Harness has separately materialized an accepted SessionEpoch, ProcessGeneration and current provider writer. Stage B therefore assigns after current-writer materialization, not inside C2.

<!-- STAGE_B1_CORRECTION_GATE_BEGIN -->
```json
{
  "schema": "mastermind.autonomy_stage_b1_correction_gate.v5",
  "architecture_revision": "v5.2-claim-then-materialize-binding",
  "protected_source_sha": "0d5c80bba8c69b5d1ed86aa3d32c9003a4252c73",
  "architecture_operation": "stage-b0-r1-real-owner-gap-repair-20260902-sol-001",
  "carrier": {
    "repository": "mastermindx-market-intelligence/Mastermind",
    "pull_request": 368,
    "branch": "sol/stage-b0-protected-source-correction-r1-20260902"
  },
  "records_paths": [
    "docs/superpowers/specs/2026-09-01-autonomy-stage-b-durable-target-transfer-design.md",
    "docs/superpowers/plans/2026-09-01-autonomy-stage-b-durable-target-transfer.md",
    "tests/test_autonomy_stage_b_durable_target_transfer_source_law.py"
  ],
  "records_only": true,
  "architecture_state": "FROZEN",
  "stage_b1_state": "HELD_PREDECESSORS",
  "predecessors": [
    "CAPACITY_C1_PROTECTED",
    "CAPACITY_C2_ROOT_BOUND_CLAIM_COMMITMENT_PROTECTED",
    "EXECUTIVE_CEO_CODEX_A_TARGET_PROTECTED",
    "EXACT_CURRENT_OHF_WRITER_MATERIALIZED"
  ],
  "next_program_wave": "CAPACITY_C2_TRANSACTIONAL_CLAIM_COMMITMENT_VERTICAL",
  "stage_b1_after_predecessors": "STAGE_B1_CEO_CODEX_INITIAL_ASSIGNMENT_VERTICAL",
  "authorized_mode_after_predecessors": "INITIAL_ASSIGNMENT",
  "authorized_surface_after_predecessors": "codex",
  "production_root_call_path": [
    "CeoIngress v2",
    "ExecutiveControlService._submit_service_intent",
    "ceo_intent.submit_intent",
    "Runtime.jobs.create_v2_orchestration_root"
  ],
  "placement_commitment_owner": "Capacity C2 through existing Executive Runtime transaction and claim owners",
  "writer_materialization_owner": "existing Operator Harness and RuntimeBinding projection",
  "assignment_owner": "first SOL_ACTION_TARGET_ASSIGNED Event on responsibility root Job",
  "production_assignment_caller": "ExecutiveControlService exact current-writer materialization/replay path after C2 commitment",
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

## Verified current source

- The production CEO v2 admission chain is real: `_submit_service_intent` calls the canonical `ceo_intent.submit_intent`, which calls `Runtime.jobs.create_v2_orchestration_root`.
- `ceo_intent.submit_intent` owns stable command replay and strict durable root reconstruction.
- checked-in `root_job_bindings` is empty and test-overlay-only; it is not assignment authority.
- current target policy has no `target_seat=ceo` plus `reasoning_surface=codex` entry.
- `AttemptRegistry.claim_job` already owns one `BEGIN IMMEDIATE` transaction over quota CAS, Attempt creation, Job transition, placement snapshot persistence and the `JOB_CLAIMED` Event.
- `runtime_binding_projection.py` does not persist a binding. It projects one only from `Runtime.current_harness_binding_source`, which requires an accepted SessionEpoch, current ProcessGeneration and provider session.
- Stage A resolves only the exact root/CEO alias, never defaults, and grants action authority only to the exact RuntimeBinding identity.
- Capacity C1 is selection evidence, not commitment. Capacity C2 remains the required modifying claim owner.

## Ordered program sequence

```text
1. PROTECT_STAGE_B0_V5_2_ARCHITECTURE
2. PROTECT_CAPACITY_C1_SELECTION
3. BUILD_CAPACITY_C2_ROOT_BOUND_CLAIM_COMMITMENT
4. ADD_DISABLED_EXECUTIVE_CEO_CODEX_A_TARGET
5. MATERIALIZE_EXACT_CURRENT_OHF_WRITER
6. RED_STAGE_B1_PRODUCTION_ROOT_COMMITMENT_AND_BINDING_CHAIN
7. IMPLEMENT_CLOSED_INITIAL_ASSIGNMENT_COMMAND_AND_EVENT
8. IMPLEMENT_TRUSTED_REPLAY_CURRENT_TRUTH_REVALIDATION
9. IMPLEMENT_COMPLETE_MAP_CURRENT_BINDING_PROJECTOR
10. INTEGRATE_EXECUTIVE_SERVICE_CURRENT_WRITER_CALLER
11. PROVE_UNCHANGED_STAGE_A_AND_EXACT_ACTOR_FENCE
12. RUN_ROW_INTEGRITY_MUTATION_REPOSITORY_AND_SECURITY_PROOF
13. INDEPENDENT_IMMUTABLE_HEAD_REVIEW
14. SOL_EXPECTED_HEAD_SOURCE_RELEASE
15. SEPARATE_DISPOSABLE_CANARY
```

The architecture source is protected first so predecessor and ownership law is durable before code waves begin. Steps 2-5 are separate dependency work. They are not permission to hide C2, target creation or provider/OHF materialization inside Stage-B1. Stage-B1 source does not START before all four predecessors are true.

## Capacity C2 handoff requirement

The already-assigned Capacity/Fleet principal owns the next program wave after C1 protects. C2 must:

- consume the exact recomputable C1 selection document as comparison evidence, not authority;
- initially support only a selected existing Worker lane that the current claim owner can verify and claim without provider I/O;
- in one existing Executive Runtime `BEGIN IMMEDIATE` transaction reread the root Job, workstream identity, selected Worker, quota row, occupancy/fence and effect facts;
- invoke or extend the existing canonical claim mutation rather than duplicating its SQL;
- claim only canonical Worker and Attempt rows;
- preserve the canonical placement snapshot on the Attempt;
- append one immutable `CAPACITY_PLACEMENT_COMMITTED` root Event in the same transaction;
- bind root, selection/evidence digests, selected worker/quota, committed Attempt and placement-snapshot digest;
- exclude RuntimeBinding id/generation, native handle and provider session because they do not exist yet;
- abort on drift, duplicate identity, conflict, stale evidence or effect uncertainty;
- never choose a second candidate in the same modifying operation;
- create no placement database, reservation service, queue, router, lease or second scheduler.

The C2 commitment authorizes later materialization of only the exact claimed Attempt under the existing provider/OHF owners. It is not Sol action-target authority by itself.

## SessionTarget predecessor requirement

The SessionTargetRegistry owner must add exactly one disabled, production-unarmed `EXECUTIVE-CEO-CODEX-A` definition on a separate bounded carrier before Stage-B1 starts. That carrier owns `config/wake_session_targets.json` and the target-definition tests. Stage-B1 consumes and fingerprints the protected target; it never edits or recreates it.

This separation preserves one owner for target vocabulary and one owner for root assignment.

## Current-writer materialization requirement

After C2 commits the root/Attempt claim, the existing Operator Harness/provider path may start or resume that exact Attempt under its own authority, effect and reconciliation laws. Stage B does not start the provider and does not add a materialization queue.

The assignment precondition is one exact current writer projected from:

```text
committed Attempt
-> accepted SessionEpoch
-> accepted current ProcessGeneration
-> exact provider session
-> runtime_binding_projection
```

No current writer yields `TARGET_RUNTIME_NOT_MATERIALIZED`. Ambiguous or effect-unknown materialization yields `EFFECT_UNKNOWN_RECONCILE_FIRST`. Neither case causes another Worker selection, Attempt claim, provider start or target assignment.

## Stage-B1 exact source ceiling

After predecessors protect, use at most six paths:

```text
control_plane/executive_runtime.py
control_plane/runtime_binding_projection.py
control_plane/sol_action_target_assignment.py
control_plane/executive_service.py
tests/test_autonomy_stage_b_initial_assignment.py
tests/test_autonomy_stage_b_durable_target_transfer_source_law.py
```

No seventh path without a finite decision request. Do not modify `control_plane/sol_action_target.py`. Do not modify `config/wake_session_targets.json`, common provider identity, Wake ledger, Slack, Agent OS, Linear, deployment, credentials or production arming.

## Complete implementation journey

1. Capacity C2 atomically validates/recomputes C1, claims the exact Worker/Attempt and appends the root claim commitment without any RuntimeBinding field.
2. The existing Operator Harness later materializes the exact current writer for the committed Attempt and reconciles any provider-side uncertainty under its own laws.
3. The existing Executive service current-writer completion/replay path derives the Stage-B command from root, C2 commitment, protected target and current binding comparisons; caller cannot supply command id or destination identity.
4. Start `BEGIN IMMEDIATE`; lookup the derived assignment command before mutable reads.
5. Revalidate the existing assignment Event if present. Replay is successful only while root, C2 commitment, target fingerprint and current binding still match.
6. Freshly validate the CEO v2 root through the existing durable provenance and `JOB_CREATED` owner.
7. Resolve the exact root-bound C2 commitment and canonical claimed Worker/Attempt.
8. Resolve the unique protected disabled `EXECUTIVE-CEO-CODEX-A` definition and project the current RuntimeBinding from the committed Attempt on the same Runtime connection.
9. Compare all command claims; append revision-one `SOL_ACTION_TARGET_ASSIGNED` once.
10. At action time, fold the root assignment, revalidate C2 and current binding, preserve the complete root/seat map and call unchanged Stage A with the actual actor RuntimeBinding.
11. Wrong, sister, stale or replacement-generation actors are observer-only/refused. A future succession architecture is required before a new generation may act.

## Replay, time, null and correction law

- C2 commitment ID derives from the root and exact C1 semantics; Stage-B command ID derives from current assignment semantics. Neither is caller supplied.
- Identical replay looks up first but then revalidates current truth; historical success is not a reusable capability.
- Same ID with changed semantics is `COMMAND_REPLAY_CONFLICT`.
- Same-root concurrent commands serialize to one append and one `EXPECTED_REVISION_MISMATCH`.
- A response loss reconciles only by the same derived ID. No carrier, alias, provider or worker failover.
- Timestamps are audit-only and never elect a destination.
- Missing root, C2 commitment, target, Worker, Attempt, current writer or binding evidence fails closed.
- V5.2 has no correction, reassignment or generation succession. Drift yields `STALE_ASSIGNED_BINDING` or a commitment conflict.

## Deterministic versus model behavior

All root/commitment lookup, schema validation, command identity, replay, transaction, Event fold, target fingerprint, RuntimeBinding projection, map preservation and Stage-A enforcement are deterministic. Model output may explain or request work but cannot select a root, worker, Attempt, alias, writer, binding, command, retry or arming state.

## Acceptance

Tests must prove:

- exact protected production root call path and v2 provenance;
- C1 selection cannot substitute for C2 claim commitment;
- C2 commitment is atomic with canonical Worker/Attempt claim and placement-snapshot persistence;
- C2 commitment contains no RuntimeBinding id/generation, native handle or provider session;
- caller/destination cannot supply carrier, Worker, Attempt, RuntimeBinding or actor authority;
- missing/foreign/cross-root/effect-unknown C2 commitment refuses;
- missing or multiple Codex CEO target definitions refuse;
- Stage-B1 never modifies or recreates the separately protected target definition;
- missing current writer returns `TARGET_RUNTIME_NOT_MATERIALIZED` with zero retry/start/assignment effect;
- command replay revalidates current root, C2 commitment, target and binding;
- moved binding/generation refuses after historical success;
- one Event under concurrency and exact changed-payload conflict;
- same alias may be shared only by roots bound to one identical RuntimeBinding;
- complete map and sibling seats are preserved;
- unchanged Stage A grants only the exact actor and refuses stale/sister actors;
- Event contains no native/provider/account/process/Slack/model data;
- Job/Attempt/Worker/OHF/Wake rows change only under their existing owners;
- source release remains default-disabled and production-disarmed.

Green CI and merge are not production proof. The later canary must use a real admitted CEO root, real C2 claim commitment and real current writer; append one assignment, authorize the exact Codex actor, refuse wrong/stale actors, restart, replay the same command, then prove Wake delivery/acknowledgement without any implicit succession.

## Stop condition

The records carrier stops at a current-compatible, three-path, reviewed V5.2 architecture. The C2 source wave stops at `BUILT_NOT_PROVEN / CLAIM_COMMITMENT_ONLY / PRODUCTION_DISARMED`. The Stage-B1 source wave stops at `BUILT_NOT_PROVEN / INITIAL_ASSIGNMENT_ONLY / PRODUCTION_DISARMED`. Production acceptance remains a separate canary and explicit Sol/Chairman gate.