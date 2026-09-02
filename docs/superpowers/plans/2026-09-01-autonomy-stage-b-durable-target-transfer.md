---
schema: mastermind.autonomy_stage_b1_plan.v5
architecture_revision: v5.1-trusted-replay-production-call-path
operation: stage-b0-r1-real-owner-gap-repair-20260902-sol-001
capability: SPEC_ONLY
production_effect: NONE
---

# Stage-B0-R1 V5.1 - Trusted Replay and Production Call Path

## Mission

Freeze the exact predecessor and implementation sequence for the first CEO Codex action-target assignment without creating a destination-selection or assignment authority beside Executive Runtime, Capacity C2, SessionTargetRegistry, RuntimeBinding or Stage A.

<!-- STAGE_B1_CORRECTION_GATE_BEGIN -->
```json
{
  "schema": "mastermind.autonomy_stage_b1_correction_gate.v5",
  "architecture_revision": "v5.1-trusted-replay-production-call-path",
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
    "CAPACITY_C2_ROOT_BOUND_COMMITMENT_PROTECTED",
    "EXECUTIVE_CEO_CODEX_A_TARGET_PROTECTED"
  ],
  "next_program_wave": "CAPACITY_C2_TRANSACTIONAL_COMMITMENT_VERTICAL",
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
  "assignment_owner": "first SOL_ACTION_TARGET_ASSIGNED Event on responsibility root Job",
  "production_assignment_caller": "ExecutiveControlService successful or identically replayed Capacity C2 completion path",
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
- `runtime_binding_projection.py` maps `openai-codex` to `codex`, reads through the current Runtime seam on an optional shared connection and persists nothing.
- Stage A resolves only the exact root/CEO alias, never defaults, and grants action authority only to the exact RuntimeBinding identity.
- Capacity C1 is selection evidence, not commitment. Capacity C2 remains the required modifying owner.

## Ordered program sequence

```text
1. PROTECT_CAPACITY_C1_SELECTION
2. BUILD_CAPACITY_C2_ROOT_BOUND_COMMITMENT
3. ADD_DISABLED_EXECUTIVE_CEO_CODEX_A_TARGET
4. PROTECT_STAGE_B0_V5_1_ARCHITECTURE
5. RED_STAGE_B1_PRODUCTION_ROOT_AND_COMMITMENT_CHAIN
6. IMPLEMENT_CLOSED_INITIAL_ASSIGNMENT_COMMAND_AND_EVENT
7. IMPLEMENT_TRUSTED_REPLAY_CURRENT_TRUTH_REVALIDATION
8. IMPLEMENT_COMPLETE_MAP_CURRENT_BINDING_PROJECTOR
9. INTEGRATE_EXECUTIVE_SERVICE_C2_COMPLETION_CALLER
10. PROVE_UNCHANGED_STAGE_A_AND_EXACT_ACTOR_FENCE
11. RUN_ROW_INTEGRITY_MUTATION_REPOSITORY_AND_SECURITY_PROOF
12. INDEPENDENT_IMMUTABLE_HEAD_REVIEW
13. SOL_EXPECTED_HEAD_SOURCE_RELEASE
14. SEPARATE_DISPOSABLE_CANARY
```

The first three steps are dependency work, not permission to hide C2 or target creation inside the records PR. Stage-B1 source does not START before all three protect.

## Capacity C2 handoff requirement

The already-assigned Capacity/Fleet principal owns the next program wave after C1 protects. C2 must:

- consume the exact recomputable C1 selection document;
- in one existing Executive Runtime transaction reread capacity, occupancy, fence and RuntimeBinding facts;
- claim only canonical Worker and Attempt rows;
- append one immutable `CAPACITY_PLACEMENT_COMMITTED` root Event;
- bind root, selection/evidence digests, worker, Attempt and RuntimeBinding id/generation;
- abort on drift, duplicate identity, conflict, stale evidence or effect uncertainty;
- never choose a second candidate in the same modifying operation;
- create no placement database, reservation service, queue, router, lease or second scheduler.

The commitment is the only Stage-B destination authority. A C1 selection, RuntimeBinding, provider identity, caller field or model statement alone must fail.

## Stage-B1 exact source ceiling

After predecessors protect, use at most seven paths:

```text
config/wake_session_targets.json
control_plane/executive_runtime.py
control_plane/runtime_binding_projection.py
control_plane/sol_action_target_assignment.py
control_plane/executive_service.py
tests/test_autonomy_stage_b_initial_assignment.py
tests/test_autonomy_stage_b_durable_target_transfer_source_law.py
```

No eighth path without a finite decision request. Do not modify `control_plane/sol_action_target.py`, common provider identity, Wake ledger, Slack, Agent OS, Linear, deployment, credentials or production arming.

## Complete implementation journey

1. Receive the successful or identically replayed C2 commitment inside the existing Executive service.
2. Derive the Stage-B command from root, commitment and target comparisons; caller cannot supply command id or destination identity.
3. Start `BEGIN IMMEDIATE`; lookup the derived assignment command before mutable reads.
4. Revalidate the existing assignment Event if present. A replay is successful only while root, C2 commitment, target fingerprint and current binding still match.
5. Freshly validate the CEO v2 root through the existing durable provenance and `JOB_CREATED` owner.
6. Resolve the exact root-bound C2 commitment and canonical claimed Worker/Attempt.
7. Resolve the unique disabled `EXECUTIVE-CEO-CODEX-A` definition and reproject the committed RuntimeBinding on the same connection.
8. Compare all command claims; append revision-one `SOL_ACTION_TARGET_ASSIGNED` once.
9. At action time, fold the root assignment, revalidate C2 and current binding, preserve the complete root/seat map and call unchanged Stage A with the actual actor RuntimeBinding.
10. Wrong, sister, stale or replacement-generation actors are observer-only/refused. A future succession architecture is required before a new generation may act.

## Replay, time, null and correction law

- Command ID derives from canonical semantics and is never caller supplied.
- Identical replay looks up first but then revalidates current truth; historical success is not a reusable capability.
- Same ID with changed semantics is `COMMAND_REPLAY_CONFLICT`.
- Same-root concurrent commands serialize to one append and one `EXPECTED_REVISION_MISMATCH`.
- A response loss reconciles only by the same derived ID. No carrier, alias, provider or worker failover.
- Timestamps are audit-only and never elect a destination.
- Missing root, commitment, target, Worker, Attempt or binding evidence fails closed.
- V5.1 has no correction, reassignment or generation succession. Drift yields `STALE_ASSIGNED_BINDING` or a commitment conflict.

## Deterministic versus model behavior

All root/commitment lookup, schema validation, command identity, replay, transaction, Event fold, target fingerprint, RuntimeBinding projection, map preservation and Stage-A enforcement are deterministic. Model output may explain or request work but cannot select a root, carrier, worker, Attempt, alias, binding, command, retry or arming state.

## Acceptance

Tests must prove:

- exact protected production root call path and v2 provenance;
- C1 selection cannot substitute for C2 commitment;
- caller/destination cannot supply carrier, Worker, Attempt, RuntimeBinding or actor authority;
- missing/foreign/cross-root/effect-unknown C2 commitment refuses;
- missing or multiple Codex CEO target definitions refuse;
- command replay revalidates current root, commitment, target and binding;
- moved binding/generation refuses after historical success;
- one Event under concurrency and exact changed-payload conflict;
- same alias may be shared only by roots bound to one identical RuntimeBinding;
- complete map and sibling seats are preserved;
- unchanged Stage A grants only the exact actor and refuses stale/sister actors;
- Event contains no native/provider/account/process/Slack/model data;
- Job/Attempt/Worker/OHF/Wake rows change only where C2 already owns them;
- source release remains default-disabled and production-disarmed.

Green CI and merge are not production proof. The later canary must use a real admitted CEO root and real C2 commitment, append one assignment, authorize the exact Codex actor, refuse wrong/stale actors, restart, replay the same command, then prove Wake delivery/acknowledgement without any implicit succession.

## Stop condition

The records carrier stops at a current-base, three-path, independently reviewed V5.1 architecture. The source wave stops at `BUILT_NOT_PROVEN / INITIAL_ASSIGNMENT_ONLY / PRODUCTION_DISARMED`. Production acceptance remains a separate canary and explicit Sol/Chairman gate.
