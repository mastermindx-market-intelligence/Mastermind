# Autonomy Closure Spine v1 — Architecture Freeze

**Status:** `SPEC_ONLY / RECORDS_ONLY / PRODUCTION_INERT`  
**Operation:** `autonomy-closure-spine-f0-20260903-sol-001`  
**Protected pickup:** `7022e70640637a4fa07f073442dc693301290e2a`

## Outcome

Close one concrete autonomy gap without building another autonomy platform:

```text
canonical terminal return
→ exact action-authoritative Sol is notified
→ one Runtime-owned semantic directive is committed
→ the existing COO cycle consumes it exactly once
→ one same-root continuation, repair, stop, or escalation transition
```

Today the transport, target, terminal-return, Wake, dialogue, Runtime, and COO owners already exist. The missing capability is a single compare-and-swap semantic directive in the existing Executive Event plane. ACF-1 is therefore the only pre-fleet implementation authorized by this architecture.

## Authority ruling

Runtime v1 recognizes exactly one directive actor class: `ACTION_TARGET`. It reuses `control_plane.sol_action_target.require_sol_action_authority(...)` and stores the resulting `SolActionTargetResolution.evidence_digest`. The resolution is evidence, never a reusable token, so authority is re-resolved inside the Runtime transaction immediately before append.

There is **no machine-authenticated `CHAIRMAN` actor in v1**. Chris remains constitutional Chairman and can direct the current action-target Sol through the human/session layer. A changed Chairman decision becomes revision N+1 submitted by the then-current exact action target. This preserves Chairman control without inventing a Chairman credential, authority registry, Slack command bus, or browser identity inside Runtime.

## Decision body

The directive body is not prose and not a generic action map. It is one exact closed `mastermind.executive_semantic_directive_body/v1` union:

- `CONTINUE`: no payload beyond schema and decision.
- `REPAIR`: one immutable `CommissionRef`, validated by `common.commission_ref.normalize_commission_ref`.
- `STOP`: one closed terminal reason.
- `ESCALATE`: one closed external-decision reason.

The outer decision and body decision must match. Canonical JSON is owned by `control_plane.ceo_intent.canonical_json_bytes`. The payload digest binds both decision and body. Nulls, lists, subclasses, arbitrary prose, extra keys, cross-decision fields, malformed source references, and bodies above 4096 canonical UTF-8 bytes fail closed.

## Existing-owner architecture

- **Executive Runtime** owns the atomic command comparison, Event append, readback, and downstream COO transaction.
- **SessionTargetRegistry / RuntimeBindingSnapshot / sol_action_target** own exact current Sol authority.
- **Executive terminal-return** owns the consumed terminal identity.
- **Wake / W3C / Agent Relay** own attention and acknowledgement, not semantic decision authority.
- **Agent Dialogue** remains transport only.
- **Existing COO cycle** maps the closed decision to one existing same-root transition.
- **Control Room** remains a read-only projection.
- **Agent OS** and **GitHub** remain organizational and implementation truth.

No new database, queue, scheduler, retry plane, watcher registry, target registry, RuntimeBinding store, transcript store, or Control Room truth store is allowed.

## Atomic behavior

One command identity binds the exact root, terminal Event identity/digest, predecessor directive, and revision. Decision fields are deliberately excluded so conflicting `CONTINUE` and `STOP` attempts collide rather than create parallel directives.

Within one existing Runtime transaction:

1. Re-read and validate the terminal Event and source identity.
2. Resolve the exact current action target from current registry and complete RuntimeBinding evidence.
3. Validate the exact body variant and canonical payload digest.
4. Compare predecessor/revision/supersession state.
5. Append at most one `EXECUTIVE_SEMANTIC_DIRECTIVE_COMMITTED` Event.
6. Re-read the committed Event for lost-response reconciliation.
7. Let the existing COO cycle consume the Event and perform one existing downstream mutation in its own accepted atomic boundary.

Exact replay is idempotent only after current authority and return facts are revalidated. Changed payload is conflict. Observer, stale generation, superseded revision, malformed body, consumed directive, or effect uncertainty is zero-effect refusal/hold.

## Supersession and terminality

History is immutable. The current action target may supersede its own unconsumed directive only in the same binding generation and only while downstream effect is known `NONE`. Target rotation alone never supersedes. Once consumed, applied, or effect-unknown, reversal requires explicit reconciliation rather than another directive.

`REPAIR`, `STOP`, and `ESCALATE` do not originate successor work. `REPAIR` can only amend/resume an existing same-root child identified by immutable source. `STOP` terminates the current boundary. `ESCALATE` holds the root for external decision without creating a Job, queue, watcher, or provider call.

## Capability boundary

Protecting these records does **not** create the Event family, modify Runtime, assign a worker, call a provider, change Wake/Relay, modify Control Room, deploy, or prove production autonomy. ACF-1 implementation remains held until this architecture is protected and the current Runtime writer releases `control_plane/executive_runtime.py`.

## Canonical closed contract

<!-- AUTONOMY_CLOSURE_SPINE_V1_CONTRACT_BEGIN -->
```json
{"schema":"mastermind.autonomy_closure_spine.v1","operation":"autonomy-closure-spine-f0-20260903-sol-001","parent_incident":"Mastermind#386","closed_duplicate_not_owner":"Mastermind#400","protected_pickup":"7022e70640637a4fa07f073442dc693301290e2a","record_paths":["docs/superpowers/specs/2026-09-03-autonomy-closure-spine-v1-design.md","docs/superpowers/plans/2026-09-03-autonomy-closure-spine-v1.md","tests/test_autonomy_closure_spine_source_law.py"],"current_state":{"capability":"SPEC_ONLY / RECORDS_ONLY / PRODUCTION_INERT","implementation_started":false,"runtime_effect":false,"provider_effect":false,"production_armed":false,"worker_assigned":false},"architecture_exception":{"default_preserved":"NO_NEW_AUTONOMY_ARCHITECTURE","concrete_blocker":"the exact action-authoritative Sol target exists, but no Runtime-owned compare-and-swap semantic directive binds one exact terminal return to one effective CONTINUE, REPAIR, STOP, or ESCALATE decision","golden_path_edge_unlocked":"terminal return -> exact Sol attention -> one effective Sol decision -> one next same-root transition","observed_incident_class":["conflicting W3C scope directives","stale C2 retreat after START_RESUMED"]},"authorized_pre_fleet_layers":["ACF-1"],"owners":{"lifecycle_and_atomic_commit":"Executive Runtime","current_sol_target":"control_plane.sol_action_target / SessionTargetRegistry / RuntimeBindingSnapshot","terminal_return":"existing Executive terminal-return owner","attention_delivery_ack":"Wake / W3C / Agent Relay","dialogue_transport":"Agent Dialogue","next_orchestration_mutation":"existing COO cycle","operational_projection":"existing Control Room","organizational_memory":"Agent OS","implementation_evidence":"GitHub"},"no_rebuild":{"new_lifecycles":[],"new_databases":[],"new_queues":[],"new_schedulers":[],"new_retry_planes":[],"new_watcher_registries":[],"new_runtime_binding_stores":[],"new_authority_registries":[],"new_transcript_stores":[],"new_control_room_truth_stores":[],"slack_as_runtime_authority":false},"acf1_semantic_directive_convergence":{"command_schema":"mastermind.executive_semantic_directive_command/v1","event_schema":"mastermind.executive_semantic_directive/v1","event_type":"EXECUTIVE_SEMANTIC_DIRECTIVE_COMMITTED","body_schema":"mastermind.executive_semantic_directive_body/v1","decisions":["CONTINUE","REPAIR","STOP","ESCALATE"],"actor_classes":["ACTION_TARGET"],"actor_authority_owner":{"module":"control_plane.sol_action_target","schema":"mastermind.sol_action_target.v1","resolver":"require_sol_action_authority","resolution_type":"SolActionTargetResolution","receipt_field":"evidence_digest","inputs":["root_job_id","SessionTargetRegistry","RuntimeBindingSnapshot","actor_binding"],"transaction_law":["resolve from current canonical inputs inside the Runtime write transaction","require state RESOLVED and action_authoritative true","bind alias, binding id, generation and reasoning surface from the same resolution","re-resolve immediately before append because the resolution is evidence, not a reusable authority token"],"non_authorities":["Slack sender or prose","browser session label","model output","provider account","carrier_reference","current Chairman chat text as a Runtime principal"]},"runtime_generated_fields":["directive_id","created_at"],"required_fields":["directive_id","root_job_id","source_job_id","source_attempt_id","source_worker_id","consumed_terminal_event_id","consumed_terminal_event_digest","current_target_alias","current_target_binding_id","current_target_binding_generation","current_target_reasoning_surface","actor_class","actor_identity_receipt_digest","carrier_reference","predecessor_directive_id","revision","decision","decision_body","decision_payload_digest","supersedes_directive_id","created_at"],"forbidden_fields":["prompt","model_output","transcript","arbitrary_slack_prose","credential","account_email","provider_secret","browser_content","raw_url","reusable_authority_token","argv","shell_command","provider_session","successor_operation_key"],"command_identity":{"scope":"one terminal-return revision","fields":["root_job_id","consumed_terminal_event_id","consumed_terminal_event_digest","predecessor_directive_id","revision"],"excludes":["decision","decision_body","decision_payload_digest","actor_class","actor_identity_receipt_digest","current_target_binding_id","current_target_binding_generation","created_at"],"reason":"CONTINUE and STOP, observer and target, or old and current target attempts must collide in one command domain instead of minting parallel directives"},"decision_body_contract":{"python_type":"built-in dict","max_canonical_utf8_bytes":4096,"canonicalizer":"control_plane.ceo_intent.canonical_json_bytes","payload_digest":"sha256(canonical_json_bytes({'decision': decision, 'decision_body': body}))","null_allowed":false,"list_allowed":false,"extension_keys_allowed":false,"outer_and_body_decision_must_match":true,"shapes":{"CONTINUE":{"schema":"mastermind.executive_semantic_directive_body/v1","decision":"CONTINUE"},"REPAIR":{"schema":"mastermind.executive_semantic_directive_body/v1","decision":"REPAIR","repair_ref":{"owner":"common.commission_ref.normalize_commission_ref","shape":{"repository":"owner/repo","commit":"40 lowercase hexadecimal characters","path":"canonical repository-relative path","content_sha256":"64 lowercase hexadecimal characters"},"authority":"immutable source identity only"}},"STOP":{"schema":"mastermind.executive_semantic_directive_body/v1","decision":"STOP","reason_code":["MISSION_COMPLETE","WORK_CANCELLED","NONRECOVERABLE_CONFLICT","SUPERSEDED_CHILD"]},"ESCALATE":{"schema":"mastermind.executive_semantic_directive_body/v1","decision":"ESCALATE","reason_code":["CHAIRMAN_DECISION_REQUIRED","EFFECT_RECONCILIATION_REQUIRED","AUTHORITY_BOUNDARY_REQUIRED","PRODUCTION_ACCEPTANCE_REQUIRED"]}},"refuses":["missing or extra keys","duplicate JSON keys","subclass values","nulls and lists","arbitrary prose or generic action maps","cross-decision fields","noncanonical repair_ref","payload over 4096 canonical UTF-8 bytes"]},"commit_semantics":{"compare_root_return_and_predecessor_revision":true,"one_effective_directive_per_return_revision":true,"exact_replay_is_idempotent_after_current_revalidation":true,"changed_payload_is_command_replay_conflict":true,"observer_sol_is_zero_effect_refusal":true,"stale_target_generation_is_zero_effect_refusal":true,"late_superseded_attempt_is_zero_effect_refusal":true,"transport_loss_after_commit_uses_event_readback":true,"transport_success_without_runtime_commit_is_not_effective":true,"continue_and_stop_cannot_both_be_effective":true},"supersession_semantics":{"history_is_immutable":true,"current_action_target_may_supersede_own_unconsumed_directive_with_same_generation_and_effect_none":true,"fresh_chairman_intervention_is_submitted_by_then_current_action_target_as_revision_n_plus_1":true,"direct_machine_authenticated_chairman_actor_in_v1":false,"consumed_applied_or_effect_unknown_requires_reconciliation":true,"normal_target_rotation_never_supersedes":true,"new_revision_binds_predecessor_and_supersedes_ids":true,"projection_reason":"DIRECTIVE_SUPERSEDED"},"consumer":{"owner":"existing COO cycle","reads_slack_prose":false,"consumes_effective_event_once":true,"consumption_and_downstream_mutation_share_one_existing_transaction":true,"downstream_command_binds_directive_event_id_digest_and_revision":true,"downstream_event_is_consumption_receipt":true,"separate_consumption_table_created":false,"directive_is_not_provider_start_retry_merge_or_deploy":true,"fixed_meanings":{"CONTINUE":"run the already-lawful next transition for the same root","REPAIR":"resume or amend only the existing same-root child identified by repair_ref","STOP":"terminalize the current child or root boundary without originating a successor","ESCALATE":"hold the root for external decision without creating a Job, queue, watcher, or provider effect"}},"closed_results":["COMMITTED","IDEMPOTENT_REPLAY","DIRECTIVE_REPLAY_CONFLICT","RETURN_NOT_TERMINAL","TERMINAL_EVENT_MISMATCH","ACTION_TARGET_AUTHORITY_INVALID","STALE_TARGET_GENERATION","DIRECTIVE_SUPERSEDED","DIRECTIVE_ALREADY_CONSUMED","DOWNSTREAM_EFFECT_UNKNOWN","INVALID_COMMAND"],"proof_requirements":["all four exact body variants and canonical payload digests","unknown, missing, extra, oversized and decision-mismatched bodies fail closed","observer, stale generation and actor receipt mismatch are zero-effect refusals","CONTINUE and STOP collide under one command identity","unconsumed same-generation supersession is immutable and deterministic","consumed, applied or effect-unknown directives cannot be reversed","REPAIR cannot originate a successor and ESCALATE creates no queue or Job","no direct CHAIRMAN actor or CHAIRMAN_SUPERSEDED projection exists in v1","restart and transport loss reconcile from the existing Event plane"]},"conditional_layers":{"ACF-2":"mission-envelope enforcement only after a golden-root falsifier proves the existing owner insufficient","ACF-3":"useful-progress semantics only after deterministic evidence proves a real gap","ACF-4":"truthful production acceptance only through existing proof owners","ACF-5":"resource finalization only through existing lifecycle owners","ACF-6":"generation compatibility only after current binding evidence requires it"},"stop_condition":{"architecture_release":"three protected records only","implementation_state_after_release":"WAITING_RUNTIME_PATH_RELEASE / needs_placement","runtime_owner_gate":"C2-R1A releases control_plane/executive_runtime.py","no_effect_claims":["no Runtime Event","no worker assignment","no provider call","no Wake or Agent Relay change","no Control Room change","no deployment","no production proof"]}}
```
<!-- AUTONOMY_CLOSURE_SPINE_V1_CONTRACT_END -->

## Release proof

The records carrier is releasable only when:

1. design and plan publish byte-semantic identical JSON;
2. the source-law test verifies every owner, body variant, conflict identity, supersession boundary, and non-goal;
3. the effective delta remains exactly these three paths;
4. repository and security checks pass on the immutable current-base head;
5. one independent non-author review approves;
6. expected-head protection is used.

No implementation worker or successor wave may start from these records alone.
