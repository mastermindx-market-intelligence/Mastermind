# Stage-B0-R1 V4 - No-Duplicate-Owner Freeze and Stage-B1 Handoff

**Date:** 2026-09-02  
**Owner:** Sol, AI CEO  
**Chairman:** Chris  
**Protected basis:** `Mastermind@cba0424f10ad6a9a917234c6740d92b19b018642`, Skillpack 1.0.1  
**Operation:** `stage-b0-r1-no-duplicate-owner-freeze-v4-20260902-sol-001`  
**Carrier:** PR #368 / `sol/stage-b0-protected-source-correction-r1-20260902`  
**State:** `RECORDS_ONLY / ARCHITECTURE_FROZEN / HOLD-FOR-SOL / PRODUCTION_INERT`

## Mission

Freeze one coherent initial-assignment vertical with no parallel binding owner:

```text
CEO-owned responsibility root
+ exact CEO-owned role-null Codex carrier writer
+ canonical disabled Codex CEO target
-> first immutable root-Job assignment Event
-> exact generation-fenced Stage-B context
-> unchanged Stage-A authority enforcement
```

The Event is the durable assignment owner. V4 does not create a predecessor receipt/store and does not require a pre-assignment Wake ACK.

<!-- STAGE_B1_CORRECTION_GATE_BEGIN -->
```json
{
  "schema": "mastermind.autonomy_stage_b1_correction_gate.v4",
  "protected_source_sha": "cba0424f10ad6a9a917234c6740d92b19b018642",
  "architecture_operation": "stage-b0-r1-no-duplicate-owner-freeze-v4-20260902-sol-001",
  "carrier": {"repository": "mastermindx-market-intelligence/Mastermind", "pull_request": 368, "branch": "sol/stage-b0-protected-source-correction-r1-20260902"},
  "records_paths": ["docs/superpowers/specs/2026-09-01-autonomy-stage-b-durable-target-transfer-design.md", "docs/superpowers/plans/2026-09-01-autonomy-stage-b-durable-target-transfer.md", "tests/test_autonomy_stage_b_durable_target_transfer_source_law.py"],
  "records_only": true,
  "runtime_effect": false,
  "provider_effect": false,
  "production_armed": false,
  "architecture_state": "FROZEN",
  "authorized_next_wave": "STAGE-B1_CEO_CODEX_INITIAL_ASSIGNMENT_VERTICAL",
  "authorized_mode": "INITIAL_ASSIGNMENT",
  "authorized_surface": "codex",
  "canonical_target_alias": "EXECUTIVE-CEO-CODEX-A",
  "durable_assignment_owner": "first SOL_ACTION_TARGET_ASSIGNED Event on responsibility root Job",
  "separate_root_binding_owner_required": false,
  "pre_assignment_wake_ack_required": false,
  "held_modes": ["SAME_ALIAS_GENERATION_SUCCESSION", "CROSS_ALIAS_RESPONSIBILITY_TRANSFER"],
  "held_surfaces": ["chatgpt-sol", "claude", "workspace-agent", "human"],
  "requires_exact_binding_generation_fence": true,
  "requires_full_map_preservation": true,
  "requires_unchanged_stage_a": true,
  "requires_separate_production_canary": true
}
```
<!-- STAGE_B1_CORRECTION_GATE_END -->

## Verified state and V4 delta

Protected source has empty/test-overlay root bindings, no Codex CEO target, role-null CEO Job/OHF evidence, an exact roleful-only RuntimeBinding source seam, implemented `codex-app-server`, exact Stage A, and real downstream Wake ACK. V3 correctly held false authority but would have created a second durable root-binding owner. V4 makes the first Stage-B Event the only owner and authorizes source implementation for `INITIAL_ASSIGNMENT` only.

## Exact source-wave scope

Repository: `mastermindx-market-intelligence/Mastermind`.

```text
config/wake_session_targets.json
control_plane/executive_runtime.py
control_plane/runtime_binding_projection.py
control_plane/sol_action_target_assignment.py
tests/test_autonomy_stage_b_initial_assignment.py
tests/test_autonomy_stage_b_durable_target_transfer_source_law.py
```

No seventh path is authorized. Do not modify `control_plane/sol_action_target.py`, common provider identity, Wake ledger, Runtime schema/migrations, Slack, Agent OS, deployment, credentials, or production arming.

## Operator handoff

### Observable mission

Ship one production-disarmed source vertical where an exact CEO-owned responsibility root is assigned to an exact current CEO-owned Codex carrier RuntimeBinding by one immutable root Event and enforced through unchanged Stage A with an exact binding-generation fence.

### Why it matters

This converts transient Sol materialization into durable, replay-safe action routing without a duplicate authority or lifecycle plane.

### Authority precedence

1. current Chairman outcome;
2. action-time protected Skillpack and universal laws;
3. protected V4 design/plan;
4. current Executive Runtime, SessionTarget, RuntimeBinding, OHF, Wake transport, and Stage-A source;
5. worker/PR/Slack/model prose as evidence only.

### Non-goals

No succession, cross-alias transfer, ChatGPT-Sol assignment, COO-root escalation, Wake write/ACK prerequisite, target enablement, new seat/role, provider-wire change, Stage-A edit, provider launch, table, migration, registry, lifecycle, queue, lease, or mutable pointer.

### Complete journey

1. Validate exact CEO-owned responsibility root and unique typed provenance.
2. Validate exact role-null CEO carrier root and current OHF Attempt.
3. Project one current `openai-codex -> codex` RuntimeBinding on the same Runtime connection.
4. Validate disabled `EXECUTIVE-CEO-CODEX-A` and target fingerprint.
5. Parse comparison claims and derive command ID.
6. In `BEGIN IMMEDIATE`, reconcile command first, fold root revision zero, validate root/carrier/current binding, and check global alias coherence.
7. Append one revision-one `SOL_ACTION_TARGET_ASSIGNED` Event.
8. Action-time: reread active root, fold Event, verify every assignment behind alias binds one exact RuntimeBinding, reproject current carrier, require bound ID/generation equality, preserve complete root map, and call unchanged Stage A.
9. Same command replays; a new generation is unavailable until future succession law.

### Data/time/null/correction law

All IDs are exact bounded values. Root status is exactly `QUEUED`, `RUNNING`, or `CHECKPOINTED`. Timestamps are audit-only and never elect a target. Missing/duplicate/conflicting provenance, target, Attempt, epoch, writer, attestation, launch decision, or binding fails closed. Same semantics replay. Same-root competitors serialize to one append and one revision mismatch. Same alias may share only the same bound ID/generation. V4 has no reassignment/succession correction. Effect uncertainty reconciles only by the same derived command ID.

### Deterministic versus model work

Code owns authority, validation, fingerprints, command ID, fold, replay, concurrency, projection, and failure states. Models may request/explain but cannot choose alias, authority, command ID, binding, generation, retry, or arming.

### Ordered implementation

<!-- STAGE_B1_IMPLEMENTATION_ORDER_BEGIN -->
```text
1. RED_V4_SOURCE_LAW_OWNER_TARGET_NO_ACK
2. ADD_DISABLED_EXECUTIVE_CEO_CODEX_A_TARGET
3. RED_ROLE_NULL_CEO_CURRENT_WRITER_PROJECTION
4. EXTEND_EXISTING_RUNTIME_READ_SEAM_WITHOUT_WEAKENING_ROLEFUL_PATH
5. RED_COMMAND_REPLAY_CONCURRENCY_AND_ALIAS_SHARING
6. IMPLEMENT_CLOSED_COMMAND_EVENT_AND_ROOT_FOLD
7. IMPLEMENT_FULL_MAP_EXACT_GENERATION_PROJECTOR
8. RED_REAL_STAGE_A_AND_STALE_GENERATION
9. INTEGRATE_UNCHANGED_STAGE_A_CONSUMER
10. RUN_ROW_INTEGRITY_FORBIDDEN_FIELD_AND_MUTATION_PROOF
11. RUN_FOCUSED_ADJACENT_FULL_AND_SECURITY_GATES
12. INDEPENDENT_IMMUTABLE_HEAD_REVIEW
13. SOL_EXPECTED_HEAD_SOURCE_RELEASE
14. SEPARATE_DISPOSABLE_PRODUCTION_CANARY
```
<!-- STAGE_B1_IMPLEMENTATION_ORDER_END -->

### Acceptance

Tests must prove root/carrier provenance and state, exact role-null OHF projection, unchanged roleful behavior, target definition, caller-inaccessible command ID/alias, one Event, replay, same-root races, multi-root same-binding sharing, different-binding conflict, complete-map/sibling preservation, exact actor, wrong actor, stale generation refusal, forbidden-field absence, and unchanged Job/Attempt/Worker/quota/OHF/Wake rows. Use real Runtime/OHF paths except explicit corruption cases.

### Stop and continuation

Stop for active path collision, material source movement, provenance or OHF owner movement, common provider-wire change, new table/registry/lifecycle, Stage-A signature change, seventh path, provider action, production arming, or unknown effect. Return exact base/head/tree/parents, six paths/blobs, contracts, target fingerprint, tests/check IDs, mutation/row-integrity receipts, immutable review, effects, and canary operation.

## Records-carrier source-law and release

The records test must prove current source archaeology plus V4 Event-as-owner, no pre-assignment ACK, one target/mode, generation fence, complete-map law, six-path ceiling, no rebuild, and production disarm. Mutations adding a predecessor owner, ACK, caller ID/alias, succession/cross-alias/ChatGPT-Sol, roleful shortcut, implicit generation transfer, destructive map, path widening, new store, or arming must fail.

PR #368 may merge only after its branch history joins current protected master without force; the effective delta remains three records paths; focused/full/security checks are terminal green; an independent exact-head review passes; and Sol performs expected-head release. The records merge authorizes source implementation only. Source release yields at most `BUILT_NOT_PROVEN / INITIAL_ASSIGNMENT_ONLY / PRODUCTION_DISARMED`; production requires a separate canary.
