# Autonomy Closure Spine v1 — Execution Program

**Status:** `SPEC_ONLY / RECORDS_ONLY / PRODUCTION_INERT`  
**Operation:** `autonomy-closure-spine-f0-20260903-sol-001`  
**Protected pickup:** `7022e70640637a4fa07f073442dc693301290e2a`

## Program objective

Deliver the shortest safe closure from a canonical terminal worker return to one effective same-root company action. This program extends existing Executive Runtime, Sol-target, terminal-return, Wake, Agent Dialogue, COO-cycle, and Control Room owners. It does not create a parallel autonomy framework.

## Wave ACF-1 — semantic directive convergence

### Observable mission

Given one exact terminal-return Event and one exact current action-authoritative Sol binding, Runtime commits at most one closed semantic directive. The existing COO cycle consumes that Event exactly once and produces one existing same-root transition or a typed zero-effect refusal/hold.

### Implementation owner and paths

Fresh archaeology controls the final bounded path set. The expected owner is `control_plane/executive_runtime.py` plus focused tests and only the smallest existing COO-cycle consumer seam. C2-R1A currently owns the Runtime path; ACF-1 must not start until that writer is protected or explicitly releases it. No alternate Event store or compatibility database is permitted.

### Ordered build

1. Add RED tests for the exact command identity, current action-target re-resolution, four body variants, conflict, supersession, replay, lost response, restart, and downstream consumption.
2. Add the command parser/normalizer using existing `canonical_json_bytes`, `normalize_commission_ref`, `SessionTargetRegistry`, `RuntimeBindingSnapshot`, and `require_sol_action_authority`.
3. Extend the existing Runtime Event transaction with `EXECUTIVE_SEMANTIC_DIRECTIVE_COMMITTED`; do not add a table.
4. Add one readback/status path over the existing Event registry for idempotency and lost-response reconciliation.
5. Wire the existing COO cycle to consume one effective directive and bind its downstream command/Event to directive Event id, digest, and revision.
6. Prove one root cannot accept competing `CONTINUE` and `STOP`, old/current target attempts, or changed bodies under the same command identity.
7. Run focused, adjacent, full repository, security, restart, mutation, and effect-unknown proof.
8. Return one Draft/Hold immutable candidate for Sol review. No Ready, merge, provider execution, host activation, or production claim.

### Complete journeys

**Continue:** terminal return → exact current target → `CONTINUE` Event → existing COO next transition.

**Repair:** terminal return → exact current target → immutable `repair_ref` → existing same-root child repair/resume only.

**Stop:** terminal return → exact current target → closed stop reason → current child/root terminal boundary; no successor.

**Escalate:** terminal return → exact current target → closed escalation reason → root held for external decision; no new Job or provider call.

**Refusal/hold:** malformed body, wrong return, observer actor, stale generation, missing target, changed revision, superseded directive, consumed directive, or effect uncertainty → no Event/downstream effect beyond the already-committed immutable history.

### Acceptance tests

- Exact `SolActionTargetResolution.evidence_digest`, alias, binding id, generation, and reasoning surface are bound and re-resolved before append.
- No direct `CHAIRMAN` Runtime actor or Slack/browser/model authority exists.
- Each body has exactly one permitted shape and deterministic digest.
- Unknown/extra/missing fields, null, list, arbitrary prose/action maps, malformed `CommissionRef`, cross-decision fields, and >4096 bytes refuse.
- Exact replay is idempotent after current revalidation; changed payload conflicts.
- `CONTINUE` and `STOP` collide in one command domain.
- Unconsumed same-generation supersession is deterministic; target rotation cannot supersede.
- Consumed/applied/effect-unknown directives cannot be reversed.
- `REPAIR` cannot originate a successor; `ESCALATE` creates no Job/queue/watcher.
- Transport loss reads back the existing Event; no blind retry or failover.
- Restart preserves the same effective directive and downstream consumption receipt.
- All user/machine-visible claims remain `BUILT_NOT_PROVEN` until a later real canary.

## Conditional later layers

ACF-2 through ACF-6 are not queued implementation. Each is evidence-gated and may begin only when a golden-root canary proves an exact gap that an existing owner cannot close:

- ACF-2: mission-envelope enforcement.
- ACF-3: useful-progress semantics.
- ACF-4: truthful production acceptance.
- ACF-5: resource finalization.
- ACF-6: generation compatibility.

## Architecture and program contract

<!-- AUTONOMY_CLOSURE_SPINE_V1_CONTRACT_BEGIN -->
```json
{"schema":"mastermind.autonomy_closure_spine.v1","operation":"autonomy-closure-spine-f0-20260903-sol-001","parent_incident":"Mastermind#386","closed_duplicate_not_owner":"Mastermind#400","protected_pickup":"7022e70640637a4fa07f073442dc693301290e2a","record_paths":["docs/superpowers/specs/2026-09-03-autonomy-closure-spine-v1-design.md","docs/superpowers/plans/2026-09-03-autonomy-closure-spine-v1.md","tests/test_autonomy_closure_spine_source_law.py"],"current_state":{"capability":"SPEC_ONLY / RECORDS_ONLY / PRODUCTION_INERT","implementation_started":false,"runtime_effect":false,"provider_effect":false,"production_armed":false,"worker_assigned":false},"architecture_exception":{"default_preserved":"NO_NEW_AUTONOMY_ARCHITECTURE","concrete_blocker":"the exact action-authoritative Sol target exists, but no Runtime-owned compare-and-swap semantic directive binds one exact terminal return to one effective CONTINUE, REPAIR, STOP, or ESCALATE decision","golden_path_edge_unlocked":"terminal return -> exact Sol attention -> one effective Sol decision -> one next same-root transition","observed_incident_class":["conflicting W3C scope directives","stale C2 retreat after START_RESUMED"]},"authorized_pre_fleet_layers":["ACF-1"],"owners":{"lifecycle_and_atomic_commit":"Executive Runtime","current_sol_target":"control_plane.sol_action_target / SessionTargetRegistry / RuntimeBindingSnapshot","terminal_return":"existing Executive terminal-return owner","attention_delivery_ack":"Wake / W3C / Agent Relay","dialogue_transport":"Agent Dialogue","next_orchestration_mutation":"existing COO cycle","operational_projection":"existing Control Room","organizational_memory":"Agent OS","implementation_evidence":"GitHub"},"no_rebuild":{"new_lifecycles":[],"new_databases":[],"new_queues":[],"new_schedulers":[],"new_retry_planes":[],"new_watcher_registries":[],"new_runtime_binding_stores":[],"new_authority_registries":[],"new_transcript_stores":[],"new_control_room_truth_stores":[],"slack_as_runtime_authority":false},"acf1_semantic_directive_convergence":{"command_schema":"mastermind.executive_semantic_directive_command/v1","event_schema":"mastermind.executive_semantic_directive/v1","event_type":"EXECUTIVE_SEMANTIC_DIRECTIVE_COMMITTED","body_schema":"mastermind.executive_semantic_directive_body/v1","decisions":["CONTINUE","REPAIR","STOP","ESCALATE"],"actor_classes":["ACTION_TARGET"],"actor_authority_owner":{"module":"control_plane.sol_action_target","schema":"mastermind.sol_action_target.v1","resolver":"require_sol_action_authority","resolution_type":"SolActionTargetResolution","receipt_field":"evidence_digest","inputs":["root_job_id","SessionTargetRegistry","RuntimeBindingSnapshot","actor_binding"],"transaction_law":["resolve from current canonical inputs inside the Runtime write transaction","require state RESOLVED and action_authoritative true","bind alias, binding id, generation and reasoning surface from the same resolution","re-resolve immediately before append because the resolution is evidence, not a reusable authority token"],"non_authorities":["Slack sender or prose","browser session label","model output","provider account","carrier_reference","current Chairman chat text as a Runtime principal"]},"runtime_generated_fields":["directive_id","created_at"],"required_fields":["directive_id","root_job_id","source_job_id","source_attempt_id","source_worker_id","consumed_terminal_event_id","consumed_terminal_event_digest","current_target_alias","current_target_binding_id","current_target_binding_generation","current_target_reasoning_surface","actor_class","actor_identity_receipt_digest","carrier_reference","predecessor_directive_id","revision","decision","decision_body","decision_payload_digest","supersedes_directive_id","created_at"],"forbidden_fields":["prompt","model_output","transcript","arbitrary_slack_prose","credential","account_email","provider_secret","browser_content","raw_url","reusable_authority_token","argv","shell_command","provider_session","successor_operation_key"],"command_identity":{"scope":"one terminal-return revision","fields":["root_job_id","consumed_terminal_event_id","consumed_terminal_event_digest","predecessor_directive_id","revision"],"excludes":["decision","decision_body","decision_payload_digest","actor_class","actor_identity_receipt_digest","current_target_binding_id","current_target_binding_generation","created_at"],"reason":"CONTINUE and STOP, observer and target, or old and current target attempts must collide in one command domain instead of minting parallel directives"},"decision_body_contract":{"python_type":"built-in dict","max_canonical_utf8_bytes":4096,"canonicalizer":"control_plane.ceo_intent.canonical_json_bytes","payload_digest":"sha256(canonical_json_bytes({'decision': decision, 'decision_body': body}))","null_allowed":false,"list_allowed":false,"extension_keys_allowed":false,"outer_and_body_decision_must_match":true,"shapes":{"CONTINUE":{"schema":"mastermind.executive_semantic_directive_body/v1","decision":"CONTINUE"},"REPAIR":{"schema":"mastermind.executive_semantic_directive_body/v1","decision":"REPAIR","repair_ref":{"owner":"common.commission_ref.normalize_commission_ref","shape":{"repository":"owner/repo","commit":"40 lowercase hexadecimal characters","path":"canonical repository-relative path","content_sha256":"64 lowercase hexadecimal characters"},"authority":"immutable source identity only"}},"STOP":{"schema":"mastermind.executive_semantic_directive_body/v1","decision":"STOP","reason_code":["MISSION_COMPLETE","WORK_CANCELLED","NONRECOVERABLE_CONFLICT","SUPERSEDED_CHILD"]},"ESCALATE":{"schema":"mastermind.executive_semantic_directive_body/v1","decision":"ESCALATE","reason_code":["CHAIRMAN_DECISION_REQUIRED","EFFECT_RECONCILIATION_REQUIRED","AUTHORITY_BOUNDARY_REQUIRED","PRODUCTION_ACCEPTANCE_REQUIRED"]}},"refuses":["missing or extra keys","duplicate JSON keys","subclass values","nulls and lists","arbitrary prose or generic action maps","cross-decision fields","noncanonical repair_ref","payload over 4096 canonical UTF-8 bytes"]},"commit_semantics":{"compare_root_return_and_predecessor_revision":true,"one_effective_directive_per_return_revision":true,"exact_replay_is_idempotent_after_current_revalidation":true,"changed_payload_is_command_replay_conflict":true,"observer_sol_is_zero_effect_refusal":true,"stale_target_generation_is_zero_effect_refusal":true,"late_superseded_attempt_is_zero_effect_refusal":true,"transport_loss_after_commit_uses_event_readback":true,"transport_success_without_runtime_commit_is_not_effective":true,"continue_and_stop_cannot_both_be_effective":true},"supersession_semantics":{"history_is_immutable":true,"current_action_target_may_supersede_own_unconsumed_directive_with_same_generation_and_effect_none":true,"fresh_chairman_intervention_is_submitted_by_then_current_action_target_as_revision_n_plus_1":true,"direct_machine_authenticated_chairman_actor_in_v1":false,"consumed_applied_or_effect_unknown_requires_reconciliation":true,"normal_target_rotation_never_supersedes":true,"new_revision_binds_predecessor_and_supersedes_ids":true,"projection_reason":"DIRECTIVE_SUPERSEDED"},"consumer":{"owner":"existing COO cycle","reads_slack_prose":false,"consumes_effective_event_once":true,"consumption_and_downstream_mutation_share_one_existing_transaction":true,"downstream_command_binds_directive_event_id_digest_and_revision":true,"downstream_event_is_consumption_receipt":true,"separate_consumption_table_created":false,"directive_is_not_provider_start_retry_merge_or_deploy":true,"fixed_meanings":{"CONTINUE":"run the already-lawful next transition for the same root","REPAIR":"resume or amend only the existing same-root child identified by repair_ref","STOP":"terminalize the current child or root boundary without originating a successor","ESCALATE":"hold the root for external decision without creating a Job, queue, watcher, or provider effect"}},"closed_results":["COMMITTED","IDEMPOTENT_REPLAY","DIRECTIVE_REPLAY_CONFLICT","RETURN_NOT_TERMINAL","TERMINAL_EVENT_MISMATCH","ACTION_TARGET_AUTHORITY_INVALID","STALE_TARGET_GENERATION","DIRECTIVE_SUPERSEDED","DIRECTIVE_ALREADY_CONSUMED","DOWNSTREAM_EFFECT_UNKNOWN","INVALID_COMMAND"],"proof_requirements":["all four exact body variants and canonical payload digests","unknown, missing, extra, oversized and decision-mismatched bodies fail closed","observer, stale generation and actor receipt mismatch are zero-effect refusals","CONTINUE and STOP collide under one command identity","unconsumed same-generation supersession is immutable and deterministic","consumed, applied or effect-unknown directives cannot be reversed","REPAIR cannot originate a successor and ESCALATE creates no queue or Job","no direct CHAIRMAN actor or CHAIRMAN_SUPERSEDED projection exists in v1","restart and transport loss reconcile from the existing Event plane"]},"conditional_layers":{"ACF-2":"mission-envelope enforcement only after a golden-root falsifier proves the existing owner insufficient","ACF-3":"useful-progress semantics only after deterministic evidence proves a real gap","ACF-4":"truthful production acceptance only through existing proof owners","ACF-5":"resource finalization only through existing lifecycle owners","ACF-6":"generation compatibility only after current binding evidence requires it"},"stop_condition":{"architecture_release":"three protected records only","implementation_state_after_release":"WAITING_RUNTIME_PATH_RELEASE / needs_placement","runtime_owner_gate":"C2-R1A releases control_plane/executive_runtime.py","no_effect_claims":["no Runtime Event","no worker assignment","no provider call","no Wake or Agent Relay change","no Control Room change","no deployment","no production proof"]}}
```
<!-- AUTONOMY_CLOSURE_SPINE_V1_CONTRACT_END -->

## Program stop condition

This F0 carrier stops after the exact three records are protected. ACF-1 remains:

```text
WAITING_ARCHITECTURE_PROTECTION
WAITING_RUNTIME_PATH_RELEASE
needs_placement
```

A separate current operation must perform implementation pickup. F0 grants no Runtime Event, worker assignment, provider call, Wake/Relay edit, Control Room edit, deployment, production arming, or fleet claim.
