# Autonomy Closure Spine v1 — Architecture Freeze

**Date:** 2026-09-03  
**Owner:** Sol, AI CEO of Mastermind-X  
**Chairman:** Chris  
**Operation:** `autonomy-closure-spine-f0-20260903-sol-001`  
**Canonical carrier:** Mastermind issue #437 / PR #438  
**Parent incident:** Mastermind issue #386  
**Protected pickup:** `7022e70640637a4fa07f073442dc693301290e2a`  
**Current compatibility read:** `13c9f2918988c5ba654e311c941f8707071ea2c4`  
**State:** `SPEC_ONLY / RECORDS_ONLY / PRODUCTION_INERT`

This is a **records-only** architecture freeze with **no implementation START**. **source protection is not production proof**.

## Executive outcome

Close one concrete autonomy gap without creating another autonomy platform:

```text
one exact terminal return
+ one exact current action-authoritative Sol target
-> one effective semantic directive
-> one once-only same-root transition
```

Stage A, SessionTargetRegistry, RuntimeBinding, and `control_plane.sol_action_target` establish **who may act**. W3C, Wake, Agent Relay, and Agent Dialogue establish **what was transported**. Neither alone establishes which `CONTINUE | REPAIR | STOP | ESCALATE` decision became effective for one exact return or which downstream mutation consumed it.

This is the single pre-fleet exception permitted by protected `NO_NEW_AUTONOMY_ARCHITECTURE`. The observed class is concrete: conflicting W3C scope rulings and a stale C2 retreat after `START_RESUMED` required human precedence recovery. The fleet cannot depend on Chairman archaeology.

## Existing-owner and no-rebuild boundary

- Executive Runtime remains the Job, Attempt, Worker, Event, command-id, and atomic transaction owner.
- `control_plane.sol_action_target`, SessionTargetRegistry, and RuntimeBindingSnapshot remain the current action-target owner.
- The existing terminal-return owner remains the source-return authority.
- W3C, Wake, and Agent Relay remain attention, delivery, and acknowledgement owners.
- Agent Dialogue remains transport only.
- The existing COO cycle remains the deterministic downstream consumer.
- Control Room remains a read-only projection.
- Agent OS remains organizational memory; GitHub remains implementation and evidence truth.

No directive database, second lifecycle, queue, scheduler, retry service, watcher registry, target registry, RuntimeBinding store, transcript store, authority registry, or Control Room truth store is authorized. Slack, browser labels, model output, and provider labels never become Runtime authority.

## V1 actor authority

V1 accepts one Runtime actor class: `ACTION_TARGET`.

For every **new append or superseding revision**, Runtime calls the existing `control_plane.sol_action_target.require_sol_action_authority(...)` with the exact root, current SessionTargetRegistry, complete RuntimeBindingSnapshot, and actor binding. It binds the returned alias, binding id, generation, reasoning surface, and `SolActionTargetResolution.evidence_digest`, then re-resolves immediately before append because the resolution is evidence, not a reusable capability.

There is no direct machine-authenticated `CHAIRMAN` Runtime actor in V1. Chris remains constitutional Chairman at the human/session layer. A fresh Chairman intervention is submitted as revision N+1 by the then-current exact action target. This preserves Chairman authority without fabricating a credential, registry, Slack command bus, or browser identity inside Runtime.

## One command conflict domain per return revision

The durable command identity is derived from exactly:

```text
root_job_id
consumed_terminal_event_id
consumed_terminal_event_digest
predecessor_directive_id
revision
```

Decision, decision body/digest, actor receipt, target binding/generation, and timestamp are excluded. Rival `CONTINUE` and `STOP` proposals, observer/current-target attempts, and old/current-target attempts therefore collide in one command domain rather than minting parallel commands.

## Replay-first effect readback

Command/Event lookup precedes current actor authorization.

When the exact command already owns an Event, Runtime validates the immutable Event bytes, command binding, terminal-return identity, payload digest, and authority receipt recorded when the effect was committed. Exact replay is idempotent **after immutable Event validation** and returns `IDEMPOTENT_REPLAY` with no new mutation.

Historical readback does not require the caller to remain the current action target. Target rotation after commit therefore cannot make the effect unknowable or convert a known commit into permanent `EFFECT_UNKNOWN`. Current action-target authorization remains mandatory only for a new append or superseding revision. Changed payload under the same command is `DIRECTIVE_REPLAY_CONFLICT`.

Replay grants no authority for a further action; it reconstructs a prior immutable effect only.

## Exact closed decision body

The body schema is `mastermind.executive_semantic_directive_body/v1`. The body is an exact built-in `dict`. Subclasses, nulls, lists, duplicate keys, extension keys, cross-decision fields, arbitrary prose, generic action maps, shell commands, provider sessions, and successor operation keys are refused. Maximum canonical UTF-8 size is 4096 bytes.

Canonical bytes use the existing `control_plane.wake_events.canonical_json_bytes`. The payload digest binds the outer decision and exact body:

```text
sha256(canonical_json_bytes({"decision": decision, "decision_body": body}))
```

Closed variants:

- `CONTINUE`: schema and decision only.
- `REPAIR`: schema, decision, and one exact `common.commission_ref.normalize_commission_ref` value identifying immutable existing repair source; it cannot originate a successor.
- `STOP`: schema, decision, and one of `MISSION_COMPLETE | WORK_CANCELLED | NONRECOVERABLE_CONFLICT | SUPERSEDED_CHILD`.
- `ESCALATE`: schema, decision, and one of `CHAIRMAN_DECISION_REQUIRED | EFFECT_RECONCILIATION_REQUIRED | AUTHORITY_BOUNDARY_REQUIRED | PRODUCTION_ACCEPTANCE_REQUIRED`.

The model may provide rationale outside the command contract, but it cannot author machine semantics.

## Runtime commit and correction law

For a new directive, one existing `BEGIN IMMEDIATE` transaction revalidates the exact terminal Event, current Attempt/Worker lineage, current action target, actor receipt, predecessor revision, consumption/effect state, and absence of a sibling effective directive before appending one command-unique Event.

The current action target may supersede its own unconsumed directive only under the same target generation, with the exact predecessor and downstream effect proven `NONE`. Fresh Chairman intervention follows that same safe pre-consumption path through the current action target as revision N+1. History remains immutable and the new revision binds both predecessor and superseded directive ids.

Consumed, applied, or effect-unknown work cannot be reversed by later prose. It requires reconciliation through the existing downstream owner. Target rotation and Slack timestamp order never supersede a directive.

A lost response after possible commit is reconciled by exact Event readback. It never authorizes a resend, alternate Sol, alternate carrier, or fallback transport. Successful transport without a Runtime Event is not an effective directive.

## Existing COO consumer and complete journeys

The existing COO cycle reads the effective Runtime Event, never Slack prose. Directive consumption and the downstream mutation share one existing Runtime transaction. The downstream command binds directive Event id, digest, and revision; the ordinary downstream Event is the consumption receipt. No second table or lifecycle exists.

- `CONTINUE`: run the already-lawful next transition for the same root.
- `REPAIR`: resume or amend only the existing same-root child identified by `repair_ref`.
- `STOP`: close only the returned source-child boundary identified by `source_job_id`; root terminalization remains existing COO/Executive Runtime law.
- `ESCALATE`: hold for external decision without creating a Job, queue, watcher, or provider effect.
- Refusal: malformed body, stale return, observer actor, stale target generation, superseded revision, consumed directive, or effect uncertainty produces no new downstream effect.

The source-child-only STOP boundary prevents a child return from ambiguously cancelling the entire root.

## Sequencing and capability ledger

| Layer | State | Ruling |
|---|---|---|
| W3C terminal wake/read | `SOURCE_PROTECTED / PRODUCTION_NOT_PROVEN` | consume existing owner |
| C2-R1A Runtime writer | `BUILT_NOT_PROVEN / OPEN_DRAFT` | release or reconcile before ACF-1 |
| MAT-S1 | `SPEC_ONLY / PREDECESSOR_HELD` | continue separately |
| Stage-B1 | `SOURCE_PROTECTED / INSTALL_NOT_PROVEN` | retain target ownership |
| Control Room | `BUILT_NOT_PROVEN / OPEN_DRAFT` | later read-only projection |
| ACF-1 | `NOT_BUILT` | only authorized new pre-fleet layer |
| ACF-2 through ACF-6 | `EVIDENCE_GATED` | no implementation authority |

ACF-1 remains:

```text
WAITING_ARCHITECTURE_PROTECTION
WAITING_RUNTIME_PATH_RELEASE
needs_placement
```

The production canary must show one real return observed by multiple Sol-capable surfaces, one exact current target, one effective directive, one once-only downstream transition, and **zero Chairman message shuttle**.

## Canonical closed contract

<!-- AUTONOMY_CLOSURE_SPINE_V1_CONTRACT_BEGIN -->
```json
{"schema":"mastermind.autonomy_closure_spine.v1","operation":"autonomy-closure-spine-f0-20260903-sol-001","parent_incident":"Mastermind#386","closed_duplicate_not_owner":"Mastermind#400","protected_pickup":"7022e70640637a4fa07f073442dc693301290e2a","record_paths":["docs/superpowers/specs/2026-09-03-autonomy-closure-spine-v1-design.md","docs/superpowers/plans/2026-09-03-autonomy-closure-spine-v1.md","tests/test_autonomy_closure_spine_source_law.py"],"current_state":{"capability":"SPEC_ONLY / RECORDS_ONLY / PRODUCTION_INERT","implementation_started":false,"runtime_effect":false,"provider_effect":false,"production_armed":false,"worker_assigned":false},"architecture_exception":{"default_preserved":"NO_NEW_AUTONOMY_ARCHITECTURE","concrete_blocker":"the exact action-authoritative Sol target exists, but no Runtime-owned compare-and-swap semantic directive binds one exact terminal return to one effective CONTINUE, REPAIR, STOP, or ESCALATE decision","golden_path_edge_unlocked":"terminal return -> exact Sol attention -> one effective Sol decision -> one next same-root transition","observed_incident_class":["conflicting W3C scope directives","stale C2 retreat after START_RESUMED"]},"authorized_pre_fleet_layers":["ACF-1"],"owners":{"lifecycle_and_atomic_commit":"Executive Runtime","current_sol_target":"control_plane.sol_action_target / SessionTargetRegistry / RuntimeBindingSnapshot","terminal_return":"existing Executive terminal-return owner","attention_delivery_ack":"Wake / W3C / Agent Relay","dialogue_transport":"Agent Dialogue","next_orchestration_mutation":"existing COO cycle","operational_projection":"existing Control Room","organizational_memory":"Agent OS","implementation_evidence":"GitHub"},"no_rebuild":{"new_lifecycles":[],"new_databases":[],"new_queues":[],"new_schedulers":[],"new_retry_planes":[],"new_watcher_registries":[],"new_runtime_binding_stores":[],"new_authority_registries":[],"new_transcript_stores":[],"new_control_room_truth_stores":[],"slack_as_runtime_authority":false},"acf1_semantic_directive_convergence":{"command_schema":"mastermind.executive_semantic_directive_command/v1","event_schema":"mastermind.executive_semantic_directive/v1","event_type":"EXECUTIVE_SEMANTIC_DIRECTIVE_COMMITTED","body_schema":"mastermind.executive_semantic_directive_body/v1","decisions":["CONTINUE","REPAIR","STOP","ESCALATE"],"actor_classes":["ACTION_TARGET"],"actor_authority_owner":{"module":"control_plane.sol_action_target","schema":"mastermind.sol_action_target.v1","resolver":"require_sol_action_authority","resolution_type":"SolActionTargetResolution","receipt_field":"evidence_digest","inputs":["root_job_id","SessionTargetRegistry","RuntimeBindingSnapshot","actor_binding"],"transaction_law":["resolve from current canonical inputs inside the Runtime write transaction","require state RESOLVED and action_authoritative true","bind alias, binding id, generation and reasoning surface from the same resolution","re-resolve immediately before append because the resolution is evidence, not a reusable authority token"],"non_authorities":["Slack sender or prose","browser session label","model output","provider account","carrier_reference","current Chairman chat text as a Runtime principal"]},"runtime_generated_fields":["directive_id","created_at"],"required_fields":["directive_id","root_job_id","source_job_id","source_attempt_id","source_worker_id","consumed_terminal_event_id","consumed_terminal_event_digest","current_target_alias","current_target_binding_id","current_target_binding_generation","current_target_reasoning_surface","actor_class","actor_identity_receipt_digest","carrier_reference","predecessor_directive_id","revision","decision","decision_body","decision_payload_digest","supersedes_directive_id","created_at"],"forbidden_fields":["prompt","model_output","transcript","arbitrary_slack_prose","credential","account_email","provider_secret","browser_content","raw_url","reusable_authority_token","argv","shell_command","provider_session","successor_operation_key"],"command_identity":{"scope":"one terminal-return revision","fields":["root_job_id","consumed_terminal_event_id","consumed_terminal_event_digest","predecessor_directive_id","revision"],"excludes":["decision","decision_body","decision_payload_digest","actor_class","actor_identity_receipt_digest","current_target_binding_id","current_target_binding_generation","created_at"],"reason":"CONTINUE and STOP, observer and target, or old and current target attempts must collide in one command domain instead of minting parallel directives"},"decision_body_contract":{"python_type":"built-in dict","max_canonical_utf8_bytes":4096,"canonicalizer":"control_plane.wake_events.canonical_json_bytes","payload_digest":"sha256(canonical_json_bytes({'decision': decision, 'decision_body': body}))","null_allowed":false,"list_allowed":false,"extension_keys_allowed":false,"outer_and_body_decision_must_match":true,"shapes":{"CONTINUE":{"schema":"mastermind.executive_semantic_directive_body/v1","decision":"CONTINUE"},"REPAIR":{"schema":"mastermind.executive_semantic_directive_body/v1","decision":"REPAIR","repair_ref":{"owner":"common.commission_ref.normalize_commission_ref","shape":{"repository":"owner/repo","commit":"40 lowercase hexadecimal characters","path":"canonical repository-relative path","content_sha256":"64 lowercase hexadecimal characters"},"authority":"immutable source identity only"}},"STOP":{"schema":"mastermind.executive_semantic_directive_body/v1","decision":"STOP","reason_code":["MISSION_COMPLETE","WORK_CANCELLED","NONRECOVERABLE_CONFLICT","SUPERSEDED_CHILD"]},"ESCALATE":{"schema":"mastermind.executive_semantic_directive_body/v1","decision":"ESCALATE","reason_code":["CHAIRMAN_DECISION_REQUIRED","EFFECT_RECONCILIATION_REQUIRED","AUTHORITY_BOUNDARY_REQUIRED","PRODUCTION_ACCEPTANCE_REQUIRED"]}},"refuses":["missing or extra keys","duplicate JSON keys","subclass values","nulls and lists","arbitrary prose or generic action maps","cross-decision fields","noncanonical repair_ref","payload over 4096 canonical UTF-8 bytes"]},"commit_semantics":{"compare_root_return_and_predecessor_revision":true,"one_effective_directive_per_return_revision":true,"exact_replay_is_idempotent_after_immutable_event_validation":true,"changed_payload_is_command_replay_conflict":true,"observer_sol_is_zero_effect_refusal":true,"stale_target_generation_is_zero_effect_refusal":true,"late_superseded_attempt_is_zero_effect_refusal":true,"transport_loss_after_commit_uses_event_readback":true,"transport_success_without_runtime_commit_is_not_effective":true,"continue_and_stop_cannot_both_be_effective":true},"replay_semantics":{"lookup_by_command_id_precedes_actor_revalidation":true,"exact_existing_event_returns_without_new_actor_authority":true,"existing_event_bytes_and_recorded_authority_receipt_are_revalidated":true,"changed_command_payload_conflicts":true,"current_target_revalidation_required_only_for_new_append_or_superseding_revision":true,"target_rotation_after_commit_does_not_block_no_effect_readback":true},"supersession_semantics":{"history_is_immutable":true,"current_action_target_may_supersede_own_unconsumed_directive_with_same_generation_and_effect_none":true,"fresh_chairman_intervention_is_submitted_by_then_current_action_target_as_revision_n_plus_1":true,"direct_machine_authenticated_chairman_actor_in_v1":false,"consumed_applied_or_effect_unknown_requires_reconciliation":true,"normal_target_rotation_never_supersedes":true,"new_revision_binds_predecessor_and_supersedes_ids":true,"projection_reason":"DIRECTIVE_SUPERSEDED"},"consumer":{"owner":"existing COO cycle","reads_slack_prose":false,"consumes_effective_event_once":true,"consumption_and_downstream_mutation_share_one_existing_transaction":true,"downstream_command_binds_directive_event_id_digest_and_revision":true,"downstream_event_is_consumption_receipt":true,"separate_consumption_table_created":false,"directive_is_not_provider_start_retry_merge_or_deploy":true,"root_terminalization_owner":"existing COO cycle / Executive Runtime","fixed_meanings":{"CONTINUE":"run the already-lawful next transition for the same root","REPAIR":"resume or amend only the existing same-root child identified by repair_ref","STOP":"close only the returned source-child boundary identified by source_job_id; root terminalization remains existing COO/Runtime law","ESCALATE":"hold the root for external decision without creating a Job, queue, watcher, or provider effect"}},"closed_results":["COMMITTED","IDEMPOTENT_REPLAY","DIRECTIVE_REPLAY_CONFLICT","RETURN_NOT_TERMINAL","TERMINAL_EVENT_MISMATCH","ACTION_TARGET_AUTHORITY_INVALID","STALE_TARGET_GENERATION","DIRECTIVE_SUPERSEDED","DIRECTIVE_ALREADY_CONSUMED","DOWNSTREAM_EFFECT_UNKNOWN","INVALID_COMMAND"],"proof_requirements":["all four exact body variants and canonical payload digests","unknown, missing, extra, oversized and decision-mismatched bodies fail closed","observer, stale generation and actor receipt mismatch are zero-effect refusals","CONTINUE and STOP collide under one command identity","replay-first readback remains possible after target rotation","unconsumed same-generation supersession is immutable and deterministic","consumed, applied or effect-unknown directives cannot be reversed","STOP closes only source_job_id and cannot terminalize the root","REPAIR cannot originate a successor and ESCALATE creates no queue or Job","no direct Chairman Runtime actor or actor-specific supersession projection exists in v1","restart and transport loss reconcile from the existing Event plane"],"conditional_layers":{"ACF-2":"mission-envelope enforcement only after a golden-root falsifier proves the existing owner insufficient","ACF-3":"useful-progress semantics only after deterministic evidence proves a real gap","ACF-4":"truthful production acceptance only through existing proof owners","ACF-5":"resource finalization only through existing lifecycle owners","ACF-6":"generation compatibility only after current binding evidence requires it"},"stop_condition":{"architecture_release":"three protected records only","implementation_state_after_release":"WAITING_RUNTIME_PATH_RELEASE / needs_placement","runtime_owner_gate":"C2-R1A releases control_plane/executive_runtime.py","no_effect_claims":["no Runtime Event","no worker assignment","no provider call","no Wake or Agent Relay change","no Control Room change","no deployment","no production proof"]}}}
```
<!-- AUTONOMY_CLOSURE_SPINE_V1_CONTRACT_END -->

## F0 release ruler

F0 may protect only after this exact three-path head passes contract extraction/equality, focused source-law, repository, and security checks; receives one independent non-author exact-head review; is reconciled against current protected source; and is released by expected head.

No implementation worker or successor wave may start from these records alone.
