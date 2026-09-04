# Autonomy Closure Spine v1 — Execution Program

**Date:** 2026-09-03  
**Owner:** Sol, AI CEO of Mastermind-X  
**Chairman:** Chris  
**Operation:** `autonomy-closure-spine-f0-20260903-sol-001`  
**Canonical carrier:** Mastermind issue #437 / PR #438  
**Protected pickup:** `7022e70640637a4fa07f073442dc693301290e2a`  
**State:** `RECORDS_ONLY / DRAFT-HOLD / IMPLEMENTATION NOT STARTED / PRODUCTION INERT`

This is a **records-only** program with **no implementation START**. Source protection is not production proof.

## Mission and critical path

Preserve:

```text
W3C-I1 -> C2-R1A -> MAT-S1 -> Stage-B1 -> Control Room
-> one golden root -> adversarial multi-root proof -> small fleet
```

Add only:

```text
terminal return
-> exact Sol attention
-> exact current ACTION_TARGET authority
-> one effective semantic directive
-> one once-only downstream COO transition
-> zero Chairman message shuttle
```

Issue #386 remains integration/acceptance. Issue #400 remains a closed duplicate. Issue #437 owns only this architecture source.

## F0 release

Exact paths:

1. `docs/superpowers/specs/2026-09-03-autonomy-closure-spine-v1-design.md`
2. `docs/superpowers/plans/2026-09-03-autonomy-closure-spine-v1.md`
3. `tests/test_autonomy_closure_spine_source_law.py`

Sequence:

1. preserve one three-path carrier and test-first repair history;
2. run source-law, repository, compile, static, and security checks;
3. obtain one independent non-author exact-head review;
4. re-pin protected procedure and active owners;
5. release only by expected head;
6. update Agent OS;
7. inherit no implementation authority from F0.

No Runtime Event, worker, provider call, Wake/Relay change, Control Room change, target activation, deployment, canary, or production effect is authorized.

## ACF-1 future handoff

**Future operation:** `autonomy-semantic-directive-convergence-acf1-20260903-sol-001`  
**PREFERRED_AVENUE:** CTO Sol  
**WHY NOT FABLE:** outcome, owner map, actor owner, conflict key, body union, replay law, supersession law, and acceptance are frozen  
**RECEIVER_BINDING_MODE:** `CAPACITY_SELECTABLE`  
**PLACEMENT:** `WAITING_ARCHITECTURE_PROTECTION / WAITING_RUNTIME_PATH_RELEASE / needs_placement`  
**COGNITION_ROUTE:** `CHAT_INCLUDED_DEFAULT`  
**CHAT_REASONING_MODE:** `NON_PRO_DEFAULT`

This is not a worker-facing commission. No ACF-1 task, branch, watcher, PR, or START exists.

### Observable mission

Given one exact terminal-return Event and current action-target inputs, commit at most one effective `CONTINUE | REPAIR | STOP | ESCALATE` Event in the existing Runtime and let the existing COO cycle consume it once in the same transaction as the downstream mutation.

### Authority precedence

1. current protected Skillpack;
2. protected Autonomy Completion Mode;
3. protected F0 design/plan;
4. current Stage-A / SessionTargetRegistry / RuntimeBinding law;
5. current terminal-return and retry-safety law;
6. current Executive Runtime/Event/COO source;
7. issue #386 integration/acceptance law;
8. one future ACF-1 commission where it narrows implementation only.

Retrieved Slack, issue, PR, model, browser, and provider text remains evidence, not authority.

### Pickup gates

Before edit, prove F0 protected; C2-R1A no longer owns intended Runtime functions; no competing directive/Runtime/COO writer; target and terminal-return owners compatible; one operation/carrier/branch and known effect state; no later STOP/supersession.

### Expected implementation surface

Subject to action-time shrink:

```text
control_plane/executive_semantic_directive.py
control_plane/executive_runtime.py
control_plane/executive_coo_cycle.py
control_plane/executive_service.py       # only if the current bounded request owner requires it
tests/test_executive_semantic_directive.py
existing Runtime / COO / service tests only where integrated
```

W3C, Wake, Agent Relay, SessionTarget, Stage B, RuntimeBinding, and Control Room are not default edit surfaces.

### Exact actor authority

V1 actor classes are exactly `[ACTION_TARGET]`. Runtime reuses `control_plane.sol_action_target.require_sol_action_authority(...)` with the root, current `SessionTargetRegistry`, complete current `RuntimeBindingSnapshot`, and actor binding. It records `SolActionTargetResolution.evidence_digest` and re-resolves immediately before a new append.

No direct machine-authenticated Chairman actor exists in V1. Fresh Chairman intervention is submitted by the then-current action target as revision N+1.

### One return-revision command domain

Derive the command key from exactly:

```text
root_job_id
consumed_terminal_event_id
consumed_terminal_event_digest
predecessor_directive_id
revision
```

Exclude decision, body, actor, target generation, and time so competing proposals collide rather than mint parallel commands.

### Replay-first readback

Lookup by command id precedes current actor revalidation. An exact existing Event is validated against immutable Event bytes, command, source return, payload digest, and the recorded authority receipt, then returned with no effect. Current action-target authority is required only before a new append or superseding revision.

Therefore response-loss recovery still succeeds after target rotation. A no-effect replay never grants new action authority; changed payload still conflicts.

### Exact body union

Body schema: `mastermind.executive_semantic_directive_body/v1`.

Canonical bytes: existing `control_plane.wake_events.canonical_json_bytes`.

Digest:

```text
sha256(canonical_json_bytes({"decision": decision, "decision_body": body}))
```

- `CONTINUE`: no additional field.
- `REPAIR`: one normalized immutable `CommissionRef` for existing same-root repair source.
- `STOP`: one closed child-terminal reason.
- `ESCALATE`: one closed external-decision reason.

Refuse extra/missing keys, duplicate JSON keys, dict subclasses, nulls, lists, arbitrary prose, generic action maps, cross-decision fields, noncanonical repair refs, and payloads over 4096 canonical UTF-8 bytes.

### New commit and safe supersession

For a new directive, one existing `BEGIN IMMEDIATE` transaction re-reads the exact terminal return, current lineage, action target, actor receipt, predecessor revision, consumption/effect state, and sibling directives; then appends one command-unique Event.

The current action target may supersede its own unconsumed directive only under the same generation with downstream effect `NONE`. Fresh Chairman intervention follows that safe pre-consumption path through the current action target as revision N+1. Consumed, applied, or effect-unknown work requires reconciliation. Target rotation and message timestamps never supersede.

### Existing COO consumer

The existing COO cycle reads only the effective Runtime Event. Consumption and downstream mutation share one transaction. The downstream command binds directive Event id/digest/revision; its ordinary Event is the receipt. No second table or lifecycle exists.

- `CONTINUE`: run the already-lawful next same-root transition.
- `REPAIR`: resume/amend only the existing child identified by `repair_ref`.
- `STOP`: close only the returned source-child boundary identified by `source_job_id`; root terminalization remains existing COO/Runtime law.
- `ESCALATE`: hold for external decision without creating a Job, queue, watcher, or provider effect.

### Closed results

```text
COMMITTED
IDEMPOTENT_REPLAY
DIRECTIVE_REPLAY_CONFLICT
RETURN_NOT_TERMINAL
TERMINAL_EVENT_MISMATCH
ACTION_TARGET_AUTHORITY_INVALID
STALE_TARGET_GENERATION
DIRECTIVE_SUPERSEDED
DIRECTIVE_ALREADY_CONSUMED
DOWNSTREAM_EFFECT_UNKNOWN
INVALID_COMMAND
```

### Implementation sequence

1. exact child pickup ACK;
2. same-SHA source/effect reconciliation;
3. continuation watcher disposition;
4. path/function freeze;
5. separate START;
6. hostile RED body/authority/conflict/replay tests;
7. pure directive validator;
8. hostile RED Runtime CAS/race/readback tests;
9. existing-transaction Event commit owner;
10. hostile RED consumer/restart/STOP-scope tests;
11. existing-COO transactional consumption;
12. bounded service seam only if required;
13. focused, mutation, repository, compile, static, and security proof;
14. one current-base Draft/HOLD PR;
15. independent exact-head review;
16. `RESULT / HOLD-FOR-SOL`, no install/canary/Ready/merge claim.

Source implementation stops at `BUILT_NOT_PROVEN / DEFAULT_DISARMED`. Live canary is separate.

### Acceptance matrix

Prove all exact body variants/digests; malformed/oversized bodies; observer and stale target refusals; `CONTINUE`/`STOP` collision; replay-first readback after target rotation; immutable unconsumed same-generation supersession; refusal to reverse consumed/applied/unknown effects; source-child-only STOP; REPAIR no-successor; ESCALATE no-queue; no direct Chairman actor; lost-response/restart Event readback; and once-only downstream consumption.

Production proof requires one real return observed by multiple Sol-capable surfaces, one current target, one effective directive, one downstream transition, and zero Chairman operational shuttling.

## Evidence-gated later layers

- ACF-2: only after a golden-root falsifier proves mission-envelope enforcement insufficient.
- ACF-3: only after deterministic evidence proves a real useful-progress gap.
- ACF-4: only through existing production-proof owners.
- ACF-5: only through existing lifecycle/resource owners.
- ACF-6: only after current binding evidence proves generation compatibility necessary.

Naming them grants no implementation authority.

## Canonical closed contract

<!-- AUTONOMY_CLOSURE_SPINE_V1_CONTRACT_BEGIN -->
```json
{"schema":"mastermind.autonomy_closure_spine.v1","operation":"autonomy-closure-spine-f0-20260903-sol-001","parent_incident":"Mastermind#386","closed_duplicate_not_owner":"Mastermind#400","protected_pickup":"7022e70640637a4fa07f073442dc693301290e2a","record_paths":["docs/superpowers/specs/2026-09-03-autonomy-closure-spine-v1-design.md","docs/superpowers/plans/2026-09-03-autonomy-closure-spine-v1.md","tests/test_autonomy_closure_spine_source_law.py"],"current_state":{"capability":"SPEC_ONLY / RECORDS_ONLY / PRODUCTION_INERT","implementation_started":false,"runtime_effect":false,"provider_effect":false,"production_armed":false,"worker_assigned":false},"architecture_exception":{"default_preserved":"NO_NEW_AUTONOMY_ARCHITECTURE","concrete_blocker":"the exact action-authoritative Sol target exists, but no Runtime-owned compare-and-swap semantic directive binds one exact terminal return to one effective CONTINUE, REPAIR, STOP, or ESCALATE decision","golden_path_edge_unlocked":"terminal return -> exact Sol attention -> one effective Sol decision -> one next same-root transition","observed_incident_class":["conflicting W3C scope directives","stale C2 retreat after START_RESUMED"]},"authorized_pre_fleet_layers":["ACF-1"],"owners":{"lifecycle_and_atomic_commit":"Executive Runtime","current_sol_target":"control_plane.sol_action_target / SessionTargetRegistry / RuntimeBindingSnapshot","terminal_return":"existing Executive terminal-return owner","attention_delivery_ack":"Wake / W3C / Agent Relay","dialogue_transport":"Agent Dialogue","next_orchestration_mutation":"existing COO cycle","operational_projection":"existing Control Room","organizational_memory":"Agent OS","implementation_evidence":"GitHub"},"no_rebuild":{"new_lifecycles":[],"new_databases":[],"new_queues":[],"new_schedulers":[],"new_retry_planes":[],"new_watcher_registries":[],"new_runtime_binding_stores":[],"new_authority_registries":[],"new_transcript_stores":[],"new_control_room_truth_stores":[],"slack_as_runtime_authority":false},"acf1_semantic_directive_convergence":{"command_schema":"mastermind.executive_semantic_directive_command/v1","event_schema":"mastermind.executive_semantic_directive/v1","event_type":"EXECUTIVE_SEMANTIC_DIRECTIVE_COMMITTED","body_schema":"mastermind.executive_semantic_directive_body/v1","decisions":["CONTINUE","REPAIR","STOP","ESCALATE"],"actor_classes":["ACTION_TARGET"],"actor_authority_owner":{"module":"control_plane.sol_action_target","schema":"mastermind.sol_action_target.v1","resolver":"require_sol_action_authority","resolution_type":"SolActionTargetResolution","receipt_field":"evidence_digest","inputs":["root_job_id","SessionTargetRegistry","RuntimeBindingSnapshot","actor_binding"],"transaction_law":["resolve from current canonical inputs inside the Runtime write transaction","require state RESOLVED and action_authoritative true","bind alias, binding id, generation and reasoning surface from the same resolution","re-resolve immediately before append because the resolution is evidence, not a reusable authority token"],"non_authorities":["Slack sender or prose","browser session label","model output","provider account","carrier_reference","current Chairman chat text as a Runtime principal"]},"runtime_generated_fields":["directive_id","created_at"],"required_fields":["directive_id","root_job_id","source_job_id","source_attempt_id","source_worker_id","consumed_terminal_event_id","consumed_terminal_event_digest","current_target_alias","current_target_binding_id","current_target_binding_generation","current_target_reasoning_surface","actor_class","actor_identity_receipt_digest","carrier_reference","predecessor_directive_id","revision","decision","decision_body","decision_payload_digest","supersedes_directive_id","created_at"],"forbidden_fields":["prompt","model_output","transcript","arbitrary_slack_prose","credential","account_email","provider_secret","browser_content","raw_url","reusable_authority_token","argv","shell_command","provider_session","successor_operation_key"],"command_identity":{"scope":"one terminal-return revision","fields":["root_job_id","consumed_terminal_event_id","consumed_terminal_event_digest","predecessor_directive_id","revision"],"excludes":["decision","decision_body","decision_payload_digest","actor_class","actor_identity_receipt_digest","current_target_binding_id","current_target_binding_generation","created_at"],"reason":"CONTINUE and STOP, observer and target, or old and current target attempts must collide in one command domain instead of minting parallel directives"},"decision_body_contract":{"python_type":"built-in dict","max_canonical_utf8_bytes":4096,"canonicalizer":"control_plane.wake_events.canonical_json_bytes","payload_digest":"sha256(canonical_json_bytes({'decision': decision, 'decision_body': body}))","null_allowed":false,"list_allowed":false,"extension_keys_allowed":false,"outer_and_body_decision_must_match":true,"shapes":{"CONTINUE":{"schema":"mastermind.executive_semantic_directive_body/v1","decision":"CONTINUE"},"REPAIR":{"schema":"mastermind.executive_semantic_directive_body/v1","decision":"REPAIR","repair_ref":{"owner":"common.commission_ref.normalize_commission_ref","shape":{"repository":"owner/repo","commit":"40 lowercase hexadecimal characters","path":"canonical repository-relative path","content_sha256":"64 lowercase hexadecimal characters"},"authority":"immutable source identity only"}},"STOP":{"schema":"mastermind.executive_semantic_directive_body/v1","decision":"STOP","reason_code":["MISSION_COMPLETE","WORK_CANCELLED","NONRECOVERABLE_CONFLICT","SUPERSEDED_CHILD"]},"ESCALATE":{"schema":"mastermind.executive_semantic_directive_body/v1","decision":"ESCALATE","reason_code":["CHAIRMAN_DECISION_REQUIRED","EFFECT_RECONCILIATION_REQUIRED","AUTHORITY_BOUNDARY_REQUIRED","PRODUCTION_ACCEPTANCE_REQUIRED"]}},"refuses":["missing or extra keys","duplicate JSON keys","subclass values","nulls and lists","arbitrary prose or generic action maps","cross-decision fields","noncanonical repair_ref","payload over 4096 canonical UTF-8 bytes"]},"commit_semantics":{"compare_root_return_and_predecessor_revision":true,"one_effective_directive_per_return_revision":true,"exact_replay_is_idempotent_after_current_revalidation":true,"changed_payload_is_command_replay_conflict":true,"observer_sol_is_zero_effect_refusal":true,"stale_target_generation_is_zero_effect_refusal":true,"late_superseded_attempt_is_zero_effect_refusal":true,"transport_loss_after_commit_uses_event_readback":true,"transport_success_without_runtime_commit_is_not_effective":true,"continue_and_stop_cannot_both_be_effective":true},"replay_semantics":{"lookup_by_command_id_precedes_actor_revalidation":true,"exact_existing_event_returns_without_new_actor_authority":true,"existing_event_bytes_and_recorded_authority_receipt_are_revalidated":true,"changed_command_payload_conflicts":true,"current_target_revalidation_required_only_for_new_append_or_superseding_revision":true,"target_rotation_after_commit_does_not_block_no_effect_readback":true},"supersession_semantics":{"history_is_immutable":true,"current_action_target_may_supersede_own_unconsumed_directive_with_same_generation_and_effect_none":true,"fresh_chairman_intervention_is_submitted_by_then_current_action_target_as_revision_n_plus_1":true,"direct_machine_authenticated_chairman_actor_in_v1":false,"consumed_applied_or_effect_unknown_requires_reconciliation":true,"normal_target_rotation_never_supersedes":true,"new_revision_binds_predecessor_and_supersedes_ids":true,"projection_reason":"DIRECTIVE_SUPERSEDED"},"consumer":{"owner":"existing COO cycle","reads_slack_prose":false,"consumes_effective_event_once":true,"consumption_and_downstream_mutation_share_one_existing_transaction":true,"downstream_command_binds_directive_event_id_digest_and_revision":true,"downstream_event_is_consumption_receipt":true,"separate_consumption_table_created":false,"directive_is_not_provider_start_retry_merge_or_deploy":true,"root_terminalization_owner":"existing COO cycle / Executive Runtime","fixed_meanings":{"CONTINUE":"run the already-lawful next transition for the same root","REPAIR":"resume or amend only the existing same-root child identified by repair_ref","STOP":"close only the returned source-child boundary identified by source_job_id; root terminalization remains existing COO/Runtime law","ESCALATE":"hold the root for external decision without creating a Job, queue, watcher, or provider effect"}},"closed_results":["COMMITTED","IDEMPOTENT_REPLAY","DIRECTIVE_REPLAY_CONFLICT","RETURN_NOT_TERMINAL","TERMINAL_EVENT_MISMATCH","ACTION_TARGET_AUTHORITY_INVALID","STALE_TARGET_GENERATION","DIRECTIVE_SUPERSEDED","DIRECTIVE_ALREADY_CONSUMED","DOWNSTREAM_EFFECT_UNKNOWN","INVALID_COMMAND"],"proof_requirements":["all four exact body variants and canonical payload digests","unknown, missing, extra, oversized and decision-mismatched bodies fail closed","observer, stale generation and actor receipt mismatch are zero-effect refusals","CONTINUE and STOP collide under one command identity","replay-first readback remains possible after target rotation","unconsumed same-generation supersession is immutable and deterministic","consumed, applied or effect-unknown directives cannot be reversed","STOP closes only source_job_id and cannot terminalize the root","REPAIR cannot originate a successor and ESCALATE creates no queue or Job","no direct CHAIRMAN actor or CHAIRMAN_SUPERSEDED projection exists in v1","restart and transport loss reconcile from the existing Event plane"],"conditional_layers":{"ACF-2":"mission-envelope enforcement only after a golden-root falsifier proves the existing owner insufficient","ACF-3":"useful-progress semantics only after deterministic evidence proves a real gap","ACF-4":"truthful production acceptance only through existing proof owners","ACF-5":"resource finalization only through existing lifecycle owners","ACF-6":"generation compatibility only after current binding evidence requires it"},"stop_condition":{"architecture_release":"three protected records only","implementation_state_after_release":"WAITING_RUNTIME_PATH_RELEASE / needs_placement","runtime_owner_gate":"C2-R1A releases control_plane/executive_runtime.py","no_effect_claims":["no Runtime Event","no worker assignment","no provider call","no Wake or Agent Relay change","no Control Room change","no deployment","no production proof"]}}
```
<!-- AUTONOMY_CLOSURE_SPINE_V1_CONTRACT_END -->

## Exact next action

Validate this exact head, obtain independent review on the same review carrier, and protect F0. Then keep ACF-1 at `WAITING_RUNTIME_PATH_RELEASE / needs_placement` until C2-R1A releases Runtime. No implementation worker or successor wave may start from this plan alone.
