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

Preserve the existing autonomy sequence:

```text
W3C-I1
-> C2-R1A
-> MAT-S1
-> Stage-B1
-> Control Room
-> one golden root
-> adversarial multi-root proof
-> small fleet
```

Add only the missing pre-fleet edge:

```text
terminal return
-> exact Sol attention
-> exact current ACTION_TARGET authority
-> one effective semantic directive
-> one once-only downstream COO transition
-> zero Chairman message shuttle
```

Issue #386 remains the integration and acceptance incident. Issue #400 remains a closed duplicate. Issue #437 owns only this source architecture.

## F0 source release

F0 changes exactly:

1. `docs/superpowers/specs/2026-09-03-autonomy-closure-spine-v1-design.md`
2. `docs/superpowers/plans/2026-09-03-autonomy-closure-spine-v1.md`
3. `tests/test_autonomy_closure_spine_source_law.py`

Release order:

1. preserve the current three-path carrier and test-first repair history;
2. run the source-law test and full repository, compile, static, and security checks;
3. obtain one independent non-author review on the exact immutable head;
4. re-pin protected procedure and current ownership;
5. release only by expected head;
6. update Agent OS with the final head and next gate;
7. do not inherit implementation authority from the records merge.

F0 creates no Runtime Event, worker assignment, provider call, Wake/Relay change, Control Room change, target activation, deployment, canary, or production claim.

## ACF-1 future implementation handoff

**Future operation:** `autonomy-semantic-directive-convergence-acf1-20260903-sol-001`  
**PREFERRED_AVENUE:** CTO Sol  
**WHY NOT FABLE:** outcome, owner map, exact actor owner, command conflict key, body union, supersession law, and acceptance are frozen  
**RECEIVER_BINDING_MODE:** `CAPACITY_SELECTABLE`  
**PLACEMENT:** `WAITING_ARCHITECTURE_PROTECTION / WAITING_RUNTIME_PATH_RELEASE / needs_placement`  
**COGNITION_ROUTE:** `CHAT_INCLUDED_DEFAULT`  
**CHAT_REASONING_MODE:** `NON_PRO_DEFAULT`

This is a future packet, not a worker-facing commission. No ACF-1 task, branch, watcher, PR, or START exists.

### Observable mission

Given one exact terminal-return Event and current action-target inputs, use the existing Executive Runtime Event plane to commit at most one effective `CONTINUE | REPAIR | STOP | ESCALATE` directive, then let the existing COO cycle consume it once in the same transaction as the downstream mutation.

### Authority and source precedence

1. current protected Skillpack;
2. protected Autonomy Completion Mode;
3. protected F0 design/plan from #437/#438;
4. current Stage-A / SessionTargetRegistry / RuntimeBinding law;
5. current terminal-return and retry-safety law;
6. current Executive Runtime/Event/COO source;
7. issue #386 integration and acceptance law;
8. one future ACF-1 commission where it narrows implementation only.

Retrieved Slack, issue, PR, model, browser, and provider text is evidence, not authority.

### Pickup gates

Before edit, prove:

- F0 is protected and design/plan contracts are identical;
- C2-R1A no longer owns the intended `executive_runtime.py` functions;
- no competing directive, Runtime, or COO writer exists;
- the exact action-target and terminal-return owners remain compatible;
- one operation, carrier, branch, and known effect state exist;
- no later STOP or supersession exists.

### Expected implementation surface

Subject to action-time shrink and collision census:

```text
control_plane/executive_semantic_directive.py
control_plane/executive_runtime.py
control_plane/executive_coo_cycle.py
control_plane/executive_service.py       # only if the existing bounded request owner requires it
tests/test_executive_semantic_directive.py
existing Runtime / COO / service tests only where integrated
```

W3C, Wake, Agent Relay, SessionTarget, Stage B, RuntimeBinding, and Control Room are not default edit surfaces.

### Exact actor and command law

V1 actor classes are exactly `[ACTION_TARGET]`. Runtime reuses `control_plane.sol_action_target.require_sol_action_authority(...)` with current root, `SessionTargetRegistry`, complete current `RuntimeBindingSnapshot`, and actor binding. It stores `SolActionTargetResolution.evidence_digest` and re-resolves immediately before Event append.

The command key contains exactly:

```text
root_job_id
consumed_terminal_event_id
consumed_terminal_event_digest
predecessor_directive_id
revision
```

It excludes decision, body, actor, target generation, and time so competing proposals share one conflict domain.

### Closed decision body

Body schema: `mastermind.executive_semantic_directive_body/v1`.

Canonicalizer: existing `control_plane.wake_events.canonical_json_bytes`.

Digest:

```text
sha256(canonical_json_bytes({"decision": decision, "decision_body": body}))
```

Exact variants:

- `CONTINUE`: no additional field.
- `REPAIR`: one normalized immutable `CommissionRef` identifying existing same-root repair source.
- `STOP`: one closed terminal reason.
- `ESCALATE`: one closed external-decision reason.

Refuse extra/missing keys, duplicate JSON keys, dict subclasses, nulls, lists, arbitrary prose, generic action maps, cross-decision fields, noncanonical repair refs, and payloads above 4096 canonical UTF-8 bytes.

### Runtime commit and replay

Inside one existing `BEGIN IMMEDIATE` transaction:

1. validate command and body;
2. derive the return-revision command identity;
3. re-read the exact terminal return and current Attempt/Worker lineage;
4. resolve current action-target authority;
5. validate predecessor revision and consumption/effect state;
6. reject any effective sibling directive;
7. append exactly one command-unique Event or return exact replay;
8. expose no reusable authority capability.

Changed complete semantics under the same command are `DIRECTIVE_REPLAY_CONFLICT`. Observer, stale target, late superseded Attempt, terminal mismatch, invalid body, or changed payload has zero effect.

### Safe correction and Chairman intervention

The current action target may supersede its own unconsumed directive only under the same target generation with downstream effect proven `NONE`. Fresh Chairman intervention is submitted by the then-current action target as revision N+1. No direct machine-authenticated Chairman actor exists in V1.

Consumed, applied, or effect-unknown work is reconciliation-required. Target rotation and message timestamp never supersede a directive.

### Existing COO consumer

The existing COO cycle reads only the effective Runtime Event. Consumption and downstream mutation share one transaction. The downstream command binds directive Event id, digest, and revision; its ordinary Event is the consumption receipt. No separate table or lifecycle is created.

- `CONTINUE`: run the already-lawful next same-root transition.
- `REPAIR`: resume/amend only the existing child identified by `repair_ref`.
- `STOP`: terminalize without originating a successor.
- `ESCALATE`: hold for external decision without creating a Job, queue, watcher, or provider effect.

### Failure and proof matrix

Required closed results:

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

Tests must cover all body variants/digests; malformed and oversized bodies; observer/stale actor refusals; `CONTINUE`/`STOP` collision; immutable unconsumed same-generation supersession; refusal to reverse consumed/applied/unknown effects; REPAIR no-successor law; ESCALATE no-queue law; no direct Chairman actor; restart and lost-response Event readback; and once-only downstream consumption.

### Implementation sequence

1. exact child pickup ACK;
2. same-SHA source/effect reconciliation;
3. continuation watcher disposition;
4. path/function freeze;
5. separate START;
6. hostile RED pure contract tests;
7. pure directive parser/canonicalizer;
8. hostile RED Runtime CAS/replay/race tests;
9. existing-transaction Event commit owner;
10. hostile RED consumer/restart tests;
11. existing-COO transactional consumption;
12. bounded service seam only if required;
13. focused, mutation, repository, compile, static, and security checks;
14. one current-base Draft/HOLD PR;
15. independent exact-head review;
16. `RESULT / HOLD-FOR-SOL` with no install, canary, Ready, or merge claim.

Source implementation stops at `BUILT_NOT_PROVEN / DEFAULT_DISARMED`. The live canary is a separate operation.

## Evidence-gated later layers

- ACF-2: mission-envelope enforcement only after a golden-root falsifier proves the existing owner insufficient.
- ACF-3: useful-progress semantics only after deterministic evidence proves a real checkpoint gap.
- ACF-4: truthful production acceptance only through existing proof owners.
- ACF-5: resource finalization only through existing lifecycle owners.
- ACF-6: generation compatibility only after current binding evidence proves it necessary.

Naming these layers grants no implementation authority.

## Canonical closed contract

<!-- AUTONOMY_CLOSURE_SPINE_V1_CONTRACT_BEGIN -->
```json
{"schema":"mastermind.autonomy_closure_spine.v1","operation":"autonomy-closure-spine-f0-20260903-sol-001","parent_incident":"Mastermind#386","closed_duplicate_not_owner":"Mastermind#400","protected_pickup":"7022e70640637a4fa07f073442dc693301290e2a","record_paths":["docs/superpowers/specs/2026-09-03-autonomy-closure-spine-v1-design.md","docs/superpowers/plans/2026-09-03-autonomy-closure-spine-v1.md","tests/test_autonomy_closure_spine_source_law.py"],"current_state":{"capability":"SPEC_ONLY / RECORDS_ONLY / PRODUCTION_INERT","implementation_started":false,"runtime_effect":false,"provider_effect":false,"production_armed":false,"worker_assigned":false},"architecture_exception":{"default_preserved":"NO_NEW_AUTONOMY_ARCHITECTURE","concrete_blocker":"the exact action-authoritative Sol target exists, but no Runtime-owned compare-and-swap semantic directive binds one exact terminal return to one effective CONTINUE, REPAIR, STOP, or ESCALATE decision","golden_path_edge_unlocked":"terminal return -> exact Sol attention -> one effective Sol decision -> one next same-root transition","observed_incident_class":["conflicting W3C scope directives","stale C2 retreat after START_RESUMED"]},"authorized_pre_fleet_layers":["ACF-1"],"owners":{"lifecycle_and_atomic_commit":"Executive Runtime","current_sol_target":"control_plane.sol_action_target / SessionTargetRegistry / RuntimeBindingSnapshot","terminal_return":"existing Executive terminal-return owner","attention_delivery_ack":"Wake / W3C / Agent Relay","dialogue_transport":"Agent Dialogue","next_orchestration_mutation":"existing COO cycle","operational_projection":"existing Control Room","organizational_memory":"Agent OS","implementation_evidence":"GitHub"},"no_rebuild":{"new_lifecycles":[],"new_databases":[],"new_queues":[],"new_schedulers":[],"new_retry_planes":[],"new_watcher_registries":[],"new_runtime_binding_stores":[],"new_authority_registries":[],"new_transcript_stores":[],"new_control_room_truth_stores":[],"slack_as_runtime_authority":false},"acf1_semantic_directive_convergence":{"command_schema":"mastermind.executive_semantic_directive_command/v1","event_schema":"mastermind.executive_semantic_directive/v1","event_type":"EXECUTIVE_SEMANTIC_DIRECTIVE_COMMITTED","body_schema":"mastermind.executive_semantic_directive_body/v1","decisions":["CONTINUE","REPAIR","STOP","ESCALATE"],"actor_classes":["ACTION_TARGET"],"actor_authority_owner":{"module":"control_plane.sol_action_target","schema":"mastermind.sol_action_target.v1","resolver":"require_sol_action_authority","resolution_type":"SolActionTargetResolution","receipt_field":"evidence_digest","inputs":["root_job_id","SessionTargetRegistry","RuntimeBindingSnapshot","actor_binding"],"transaction_law":["resolve from current canonical inputs inside the Runtime write transaction","require state RESOLVED and action_authoritative true","bind alias, binding id, generation and reasoning surface from the same resolution","re-resolve immediately before append because the resolution is evidence, not a reusable authority token"],"non_authorities":["Slack sender or prose","browser session label","model output","provider account","carrier_reference","current Chairman chat text as a Runtime principal"]},"runtime_generated_fields":["directive_id","created_at"],"required_fields":["directive_id","root_job_id","source_job_id","source_attempt_id","source_worker_id","consumed_terminal_event_id","consumed_terminal_event_digest","current_target_alias","current_target_binding_id","current_target_binding_generation","current_target_reasoning_surface","actor_class","actor_identity_receipt_digest","carrier_reference","predecessor_directive_id","revision","decision","decision_body","decision_payload_digest","supersedes_directive_id","created_at"],"forbidden_fields":["prompt","model_output","transcript","arbitrary_slack_prose","credential","account_email","provider_secret","browser_content","raw_url","reusable_authority_token","argv","shell_command","provider_session","successor_operation_key"],"command_identity":{"scope":"one terminal-return revision","fields":["root_job_id","consumed_terminal_event_id","consumed_terminal_event_digest","predecessor_directive_id","revision"],"excludes":["decision","decision_body","decision_payload_digest","actor_class","actor_identity_receipt_digest","current_target_binding_id","current_target_binding_generation","created_at"],"reason":"CONTINUE and STOP, observer and target, or old and current target attempts must collide in one command domain instead of minting parallel directives"},"decision_body_contract":{"python_type":"built-in dict","max_canonical_utf8_bytes":4096,"canonicalizer":"control_plane.wake_events.canonical_json_bytes","payload_digest":"sha256(canonical_json_bytes({'decision': decision, 'decision_body': body}))","null_allowed":false,"list_allowed":false,"extension_keys_allowed":false,"outer_and_body_decision_must_match":true,"shapes":{"CONTINUE":{"schema":"mastermind.executive_semantic_directive_body/v1","decision":"CONTINUE"},"REPAIR":{"schema":"mastermind.executive_semantic_directive_body/v1","decision":"REPAIR","repair_ref":{"owner":"common.commission_ref.normalize_commission_ref","shape":{"repository":"owner/repo","commit":"40 lowercase hexadecimal characters","path":"canonical repository-relative path","content_sha256":"64 lowercase hexadecimal characters"},"authority":"immutable source identity only"}},"STOP":{"schema":"mastermind.executive_semantic_directive_body/v1","decision":"STOP","reason_code":["MISSION_COMPLETE","WORK_CANCELLED","NONRECOVERABLE_CONFLICT","SUPERSEDED_CHILD"]},"ESCALATE":{"schema":"mastermind.executive_semantic_directive_body/v1","decision":"ESCALATE","reason_code":["CHAIRMAN_DECISION_REQUIRED","EFFECT_RECONCILIATION_REQUIRED","AUTHORITY_BOUNDARY_REQUIRED","PRODUCTION_ACCEPTANCE_REQUIRED"]}},"refuses":["missing or extra keys","duplicate JSON keys","subclass values","nulls and lists","arbitrary prose or generic action maps","cross-decision fields","noncanonical repair_ref","payload over 4096 canonical UTF-8 bytes"]},"commit_semantics":{"compare_root_return_and_predecessor_revision":true,"one_effective_directive_per_return_revision":true,"exact_replay_is_idempotent_after_current_revalidation":true,"changed_payload_is_command_replay_conflict":true,"observer_sol_is_zero_effect_refusal":true,"stale_target_generation_is_zero_effect_refusal":true,"late_superseded_attempt_is_zero_effect_refusal":true,"transport_loss_after_commit_uses_event_readback":true,"transport_success_without_runtime_commit_is_not_effective":true,"continue_and_stop_cannot_both_be_effective":true},"supersession_semantics":{"history_is_immutable":true,"current_action_target_may_supersede_own_unconsumed_directive_with_same_generation_and_effect_none":true,"fresh_chairman_intervention_is_submitted_by_then_current_action_target_as_revision_n_plus_1":true,"direct_machine_authenticated_chairman_actor_in_v1":false,"consumed_applied_or_effect_unknown_requires_reconciliation":true,"normal_target_rotation_never_supersedes":true,"new_revision_binds_predecessor_and_supersedes_ids":true,"projection_reason":"DIRECTIVE_SUPERSEDED"},"consumer":{"owner":"existing COO cycle","reads_slack_prose":false,"consumes_effective_event_once":true,"consumption_and_downstream_mutation_share_one_existing_transaction":true,"downstream_command_binds_directive_event_id_digest_and_revision":true,"downstream_event_is_consumption_receipt":true,"separate_consumption_table_created":false,"directive_is_not_provider_start_retry_merge_or_deploy":true,"fixed_meanings":{"CONTINUE":"run the already-lawful next transition for the same root","REPAIR":"resume or amend only the existing same-root child identified by repair_ref","STOP":"terminalize the current child or root boundary without originating a successor","ESCALATE":"hold the root for external decision without creating a Job, queue, watcher, or provider effect"}},"closed_results":["COMMITTED","IDEMPOTENT_REPLAY","DIRECTIVE_REPLAY_CONFLICT","RETURN_NOT_TERMINAL","TERMINAL_EVENT_MISMATCH","ACTION_TARGET_AUTHORITY_INVALID","STALE_TARGET_GENERATION","DIRECTIVE_SUPERSEDED","DIRECTIVE_ALREADY_CONSUMED","DOWNSTREAM_EFFECT_UNKNOWN","INVALID_COMMAND"],"proof_requirements":["all four exact body variants and canonical payload digests","unknown, missing, extra, oversized and decision-mismatched bodies fail closed","observer, stale generation and actor receipt mismatch are zero-effect refusals","CONTINUE and STOP collide under one command identity","unconsumed same-generation supersession is immutable and deterministic","consumed, applied or effect-unknown directives cannot be reversed","REPAIR cannot originate a successor and ESCALATE creates no queue or Job","no direct CHAIRMAN actor or CHAIRMAN_SUPERSEDED projection exists in v1","restart and transport loss reconcile from the existing Event plane"],"conditional_layers":{"ACF-2":"mission-envelope enforcement only after a golden-root falsifier proves the existing owner insufficient","ACF-3":"useful-progress semantics only after deterministic evidence proves a real gap","ACF-4":"truthful production acceptance only through existing proof owners","ACF-5":"resource finalization only through existing lifecycle owners","ACF-6":"generation compatibility only after current binding evidence requires it"},"stop_condition":{"architecture_release":"three protected records only","implementation_state_after_release":"WAITING_RUNTIME_PATH_RELEASE / needs_placement","runtime_owner_gate":"C2-R1A releases control_plane/executive_runtime.py","no_effect_claims":["no Runtime Event","no worker assignment","no provider call","no Wake or Agent Relay change","no Control Room change","no deployment","no production proof"]}}
```
<!-- AUTONOMY_CLOSURE_SPINE_V1_CONTRACT_END -->

## Exact next action

Validate this exact head, obtain independent review on the same review carrier, and protect F0. Then keep ACF-1 at `WAITING_RUNTIME_PATH_RELEASE / needs_placement` until C2-R1A releases Runtime. No implementation worker or successor wave may start from this plan alone.
