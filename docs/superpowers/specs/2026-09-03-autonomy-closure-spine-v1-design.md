# Autonomy Closure Spine v1 — Architecture Freeze

**Date:** 2026-09-03  
**Owner:** Sol, AI CEO of Mastermind-X  
**Chairman:** Chris  
**Operation:** `autonomy-closure-spine-f0-20260903-sol-001`  
**Canonical Git carrier:** Mastermind issue #437  
**Parent incident:** Mastermind issue #386  
**Protected pickup:** `mastermindx-market-intelligence/Mastermind@7022e70640637a4fa07f073442dc693301290e2a`  
**Status:** `SPEC_ONLY / RECORDS_ONLY / PRODUCTION_INERT`

This is a **records-only** architecture freeze. It creates no implementation worker, Runtime Event, provider action, deployment, canary, or fleet effect. There is **no implementation START**. Source protection is not production proof.

## 1. Executive ruling

Mastermind already has the correct autonomy owners. It does not need another orchestrator, database, queue, retry service, watcher registry, target registry, or Slack command bus.

One contract is missing:

```text
one exact terminal return
+ one exact current action-authoritative Sol target
-> one machine-authoritative semantic decision
-> one downstream same-root transition
```

Stage A, Stage B and RuntimeBinding answer **who may act**. Wake, W3C, Agent Relay and Agent Dialogue answer **what was transported**. Neither currently establishes **which `CONTINUE | REPAIR | STOP | ESCALATE` decision became effective** for one exact return and which transition consumed it.

That is the permitted exception to protected `NO_NEW_AUTONOMY_ARCHITECTURE`. It closes an observed golden-path blocker rather than starting a generalized platform.

## 2. Observed failure class

The W3C carrier accumulated conflicting 14-, 16-, 19- and 25-path action-looking directives before a later Chairman correction established precedence. The C2 carrier received a stale retreat after a valid `START_RESUMED` and required a later Chairman correction.

Human procedure recovered both cases. Runtime could not reject the stale semantic decision because no canonical directive revision and conflict domain existed. A fleet must not depend on Chairman archaeology to recover this class.

## 3. Existing owners

| Fact | Canonical owner |
|---|---|
| Job, Attempt, Worker, Event and atomic command commit | Executive Runtime |
| exact current Sol target and generation | SessionTargetRegistry / RuntimeBinding / Stage B |
| exact terminal return | existing Executive terminal-return owner |
| attention, delivery and acknowledgement | Wake / W3C / Agent Relay |
| dialogue and Slack transport | Agent Dialogue |
| next deterministic orchestration mutation | existing COO cycle |
| operational display | existing Control Room |
| durable organizational memory | Agent OS |
| code, review, CI and immutable evidence | GitHub |

Transport text never grants directive authority. `carrier_reference` is provenance only.

## 4. Current collision map

- W3C-I1 source is protected through PR #427 / merge `a945e76befb34d15d0ab0e369b4197901883bb16`; it remains default-disarmed and is consumed, not rebuilt.
- C2-R1A PR #415 remains the active `control_plane/executive_runtime.py` writer. ACF-1 implementation waits for protection or explicit path release.
- MAT-S1 issue #430 remains predecessor-held and owns CEO carrier materialization/current-writer evidence.
- Stage-B V6.1 remains the target-assignment owner.
- Control Room PR #326 remains the active projection/UI writer.
- issue #386 remains the canonical integration and production-acceptance incident; issue #400 remains a closed duplicate.

ACF-1 is therefore `WAITING_ARCHITECTURE_PROTECTION / WAITING_RUNTIME_PATH_RELEASE / needs_placement`.

## 5. Canonical directive family

The first implementation vertical will extend the existing Executive Event plane with:

```text
command schema: mastermind.executive_semantic_directive_command/v1
event schema:   mastermind.executive_semantic_directive/v1
event type:     EXECUTIVE_SEMANTIC_DIRECTIVE_COMMITTED
```

The Runtime generates `directive_id` and `created_at`. The caller supplies no reusable authority token.

The closed directive binds:

```text
root Job
source Job / Attempt / Worker
terminal-return Event id and digest
current target alias / binding id / generation / reasoning surface
actor class and identity receipt digest
carrier provenance
predecessor directive and revision
decision + closed decision_body + canonical payload digest
explicit supersession identity
Runtime-owned timestamp
```

Raw prompts, model output, transcript text, arbitrary Slack prose, credentials, emails, provider secrets, browser content and raw URLs are forbidden.

## 6. One conflict domain per return revision

The idempotency command key is derived only from:

```text
root_job_id
consumed_terminal_event_id
consumed_terminal_event_digest
predecessor_directive_id
revision
```

It deliberately excludes decision, decision body/digest, actor identity, target binding/generation and wall-clock time.

This is load-bearing. `CONTINUE` and `STOP`, observer and target, or old and current target attempts must collide in **one command domain**. They may not mint parallel commands merely because their proposed payloads or actor observations differ.

The transaction then re-resolves the current target and actor and validates the complete payload. Exact same command and same complete semantics replays idempotently. Same command with changed semantics is `COMMAND_REPLAY_CONFLICT`.

## 7. Commit law

Inside one existing Runtime transaction:

1. validate the closed command and derive its return-revision command identity;
2. read the exact terminal-return source and prove its Job/Attempt/Worker remains canonical;
3. re-resolve the current target and actor identity at the effect boundary;
4. read the predecessor directive and its consumption/effect state;
5. prove no effective directive already exists for the same return revision;
6. append exactly one directive Event or return the exact existing replay;
7. expose no authority-bearing object outside the transaction.

Required refusals include:

```text
SOURCE_RETURN_MISSING
SOURCE_RETURN_CONFLICT
SOURCE_ATTEMPT_NOT_CURRENT
TARGET_MISSING
TARGET_CONFLICT
TARGET_GENERATION_STALE
ACTOR_OBSERVER_ONLY
ACTOR_IDENTITY_INVALID
PREDECESSOR_DIRECTIVE_CONFLICT
COMMAND_REPLAY_CONFLICT
DIRECTIVE_ALREADY_COMMITTED
CHAIRMAN_AUTHORITY_INVALID
DIRECTIVE_EFFECT_UNKNOWN
DIRECTIVE_CONSUMPTION_CONFLICT
DOWNSTREAM_ALREADY_APPLIED
```

An old target, observer Sol, stale terminal digest, late superseded Attempt or changed payload has zero effect.

## 8. Supersession and post-consumption safety

Directive history is immutable.

A Chairman may supersede a directive only when the predecessor is **not consumed** and the downstream effect is proven `NONE`. The new revision binds both `predecessor_directive_id` and `supersedes_directive_id`.

A consumed directive, an applied downstream mutation, or any downstream `EFFECT_UNKNOWN` cannot be reversed by publishing a later directive. That is a **post-consumption reversal** and must return `DIRECTIVE_RECONCILIATION_REQUIRED` until the existing downstream owner proves what occurred and supplies a lawful correction path.

Target rotation alone never supersedes an existing directive. Slack timestamp ordering never supersedes anything.

## 9. Consumer and consumption receipt

The existing COO cycle is the first machine consumer. It reads the effective directive Event, never Slack prose.

Its downstream command binds:

```text
directive Event id
directive Event digest
directive revision
```

The ordinary downstream Event is the consumption receipt. No separate consumption table or lifecycle is created.

The consumer compares the latest effective revision immediately before mutation. Restart or exact replay may reconstruct the consumed state but cannot apply the mutation twice.

A directive does not itself start a provider, retry an uncertain effect, merge a PR, deploy production, grant authority, or accept the root.

## 10. Transport uncertainty

```text
request proven not submitted -> NOT_APPLIED
exact Runtime Event found -> APPLIED
submission may have crossed boundary and readback unavailable -> EFFECT_UNKNOWN
```

Response loss after a committed Event is reconciled by Event readback. It never authorizes a resend, alternate Sol, alternate carrier, or fallback transport. Successful Slack delivery without a Runtime Event is not an effective directive.

## 11. Product projection

After the active Control Room carrier releases its paths, the existing Control Room may project:

```text
AWAITING_SEMANTIC_DIRECTIVE
DIRECTIVE_COMMITTED
DIRECTIVE_CONSUMED
STALE_DIRECTIVE_REJECTED
CONFLICTING_DIRECTIVE_REJECTED
CHAIRMAN_SUPERSEDED
DIRECTIVE_EFFECT_UNKNOWN
DIRECTIVE_RECONCILIATION_REQUIRED
```

The projection remains read-only and non-authoritative.

## 12. Follow-on layers

Only ACF-1 is authorized before first-fleet proof.

- **ACF-2 mission-envelope enforcement:** starts only after a golden root proves an admission/accounting gap; reuse DelegationPacket and Executive admission.
- **ACF-3 useful progress versus heartbeat:** starts only after the stall falsifier cannot close through current checkpoints/Events.
- **ACF-4 truthful production acceptance:** starts only after one real result exposes a missing acceptance receipt.
- **ACF-5 resource finalization:** starts only from resources actually created by the installed golden root and extends each current owner.
- **ACF-6 compatibility receipt:** starts only after an installed producer/consumer mismatch is reproduced and extends release/capability owners.

Naming these layers grants no implementation authority.

## 13. ACF-1 acceptance

The deterministic source vertical must prove:

- two observers, one current target, observer refused;
- old target generation refused after rotation;
- exact replay returns one Event;
- `CONTINUE`/`STOP` race yields one effective directive;
- changed payload conflicts in the same command domain;
- stale/late terminal evidence refuses;
- pre-consumption Chairman supersession preserves history;
- post-consumption reversal is reconciliation-required;
- response loss after commit uses readback;
- Slack delivery without Runtime commit is ineffective;
- COO consumption binds the directive Event and applies once after restart;
- no new store, queue, lifecycle, retry plane, watcher owner or target registry exists.

Production proof requires one real terminal return observed by at least two Sol-capable surfaces, one current action target, one effective directive, one downstream transition, and **zero Chairman message shuttle**.

ACF-1 must ship as one independently useful vertical, but source merge remains `BUILT_NOT_PROVEN / DEFAULT_DISARMED` until the real canary.

## 14. Routing and stop

```text
future operation: autonomy-semantic-directive-convergence-acf1-20260903-sol-001
PREFERRED_AVENUE: CTO Sol
WHY NOT FABLE: Chairman outcome, owner map, command identity, supersession law, failure matrix and acceptance are frozen
RECEIVER_BINDING_MODE: CAPACITY_SELECTABLE
PLACEMENT_STATE: WAITING_ARCHITECTURE_PROTECTION / WAITING_RUNTIME_PATH_RELEASE / needs_placement
COGNITION_ROUTE: CHAT_INCLUDED_DEFAULT
CHAT_REASONING_MODE: NON_PRO_DEFAULT
```

No worker-facing commission, implementation branch, watcher or START exists.

F0 stops at one exact three-path Draft/HOLD PR with source-law proof, terminal hosted repository/security checks and one independent exact-head review. It creates no Runtime, worker, provider, deployment, canary or fleet effect.

## 15. Durable contract

<!-- AUTONOMY_CLOSURE_SPINE_V1_CONTRACT_BEGIN -->
```json
{"schema":"mastermind.autonomy_closure_spine.v1","operation":"autonomy-closure-spine-f0-20260903-sol-001","parent_incident":"Mastermind#386","closed_duplicate_not_owner":"Mastermind#400","protected_pickup":"7022e70640637a4fa07f073442dc693301290e2a","current_state":{"capability":"SPEC_ONLY / RECORDS_ONLY / PRODUCTION_INERT","implementation_started":false,"runtime_effect":false,"provider_effect":false,"production_armed":false,"worker_assigned":false},"architecture_exception":{"default_preserved":"NO_NEW_AUTONOMY_ARCHITECTURE","concrete_blocker":"the exact action-authoritative Sol target exists, but no Runtime-owned compare-and-swap semantic directive binds one exact return to one effective CONTINUE, REPAIR, STOP, or ESCALATE decision","golden_path_edge_unlocked":"terminal return -> exact Sol attention -> one effective Sol decision -> one next same-root transition","observed_incident_class":["conflicting W3C scope directives","stale C2 retreat after START_RESUMED"]},"authorized_pre_fleet_layers":["ACF-1"],"owners":{"lifecycle_and_atomic_commit":"Executive Runtime","current_sol_target":"SessionTargetRegistry / RuntimeBinding / Stage B","terminal_return":"existing Executive terminal-return owner","attention_delivery_ack":"Wake / W3C / Agent Relay","dialogue_transport":"Agent Dialogue","next_orchestration_mutation":"existing COO cycle","operational_projection":"existing Control Room","organizational_memory":"Agent OS","implementation_evidence":"GitHub"},"no_rebuild":{"new_lifecycles":[],"new_databases":[],"new_queues":[],"new_schedulers":[],"new_retry_planes":[],"new_watcher_registries":[],"new_runtime_binding_stores":[],"new_authority_registries":[],"new_transcript_stores":[],"new_control_room_truth_stores":[],"slack_as_runtime_authority":false},"acf1_semantic_directive_convergence":{"command_schema":"mastermind.executive_semantic_directive_command/v1","event_schema":"mastermind.executive_semantic_directive/v1","event_type":"EXECUTIVE_SEMANTIC_DIRECTIVE_COMMITTED","decisions":["CONTINUE","REPAIR","STOP","ESCALATE"],"actor_classes":["ACTION_TARGET","CHAIRMAN"],"runtime_generated_fields":["directive_id","created_at"],"required_fields":["directive_id","root_job_id","source_job_id","source_attempt_id","source_worker_id","consumed_terminal_event_id","consumed_terminal_event_digest","current_target_alias","current_target_binding_id","current_target_binding_generation","current_target_reasoning_surface","actor_class","actor_identity_receipt_digest","carrier_reference","predecessor_directive_id","revision","decision","decision_body","decision_payload_digest","supersedes_directive_id","created_at"],"forbidden_fields":["prompt","model_output","transcript","arbitrary_slack_prose","credential","account_email","provider_secret","browser_content","raw_url","reusable_authority_token"],"command_identity":{"scope":"one terminal-return revision","fields":["root_job_id","consumed_terminal_event_id","consumed_terminal_event_digest","predecessor_directive_id","revision"],"excludes":["decision","decision_body","decision_payload_digest","actor_class","actor_identity_receipt_digest","current_target_binding_id","current_target_binding_generation","created_at"],"reason":"CONTINUE and STOP, observer and target, or old and current target attempts must collide in one command domain instead of minting parallel directives"},"authority_semantics":{"carrier_reference_is_provenance_only":true,"runtime_reresolves_current_target_and_actor":true,"model_slack_browser_and_provider_labels_grant_no_authority":true},"commit_semantics":{"compare_root_return_and_predecessor_revision":true,"one_effective_directive_per_return_revision":true,"exact_replay_is_idempotent_after_current_revalidation":true,"changed_payload_is_command_replay_conflict":true,"observer_sol_is_zero_effect_refusal":true,"stale_target_generation_is_zero_effect_refusal":true,"late_superseded_attempt_is_zero_effect_refusal":true,"transport_loss_after_commit_uses_event_readback":true,"transport_success_without_runtime_commit_is_not_effective":true,"continue_and_stop_cannot_both_be_effective":true},"supersession_semantics":{"history_is_immutable":true,"chairman_may_supersede_only_before_consumption_with_downstream_effect_none":true,"consumed_applied_or_effect_unknown_requires_reconciliation":true,"normal_target_rotation_never_supersedes":true,"new_revision_binds_predecessor_and_supersedes_ids":true},"consumer":{"owner":"existing COO cycle","reads_slack_prose":false,"consumes_effective_event_once":true,"downstream_command_binds_directive_event_id_digest_and_revision":true,"downstream_event_is_consumption_receipt":true,"separate_consumption_table_created":false,"directive_is_not_provider_start_retry_merge_or_deploy":true}},"conditional_follow_on_layers":{"ACF-2":{"name":"mission-envelope enforcement","start_gate":"post-golden-root evidence of admission/accounting gap","reuse_owner":"existing DelegationPacket and Executive admission"},"ACF-3":{"name":"useful-progress versus heartbeat","start_gate":"post-golden-root stall falsifier cannot close through checkpoints","reuse_owner":"existing Attempt checkpoint and Event plane"},"ACF-4":{"name":"truthful production acceptance","start_gate":"one real golden-root result exists","reuse_owner":"existing root Event and production-proof owners"},"ACF-5":{"name":"resource finalization","start_gate":"installed golden root exposes concrete required resources","reuse_owner":"the existing owner of each created resource"},"ACF-6":{"name":"producer-consumer compatibility receipt","start_gate":"an installed-generation incompatibility is reproduced","reuse_owner":"existing release and capability owners"}},"acf1_routing":{"future_operation_key":"autonomy-semantic-directive-convergence-acf1-20260903-sol-001","preferred_avenue":"CTO Sol","why_not_fable":"the Chairman outcome, owner map, event semantics, failure matrix, no-rebuild boundaries, and acceptance are frozen","receiver_binding_mode":"CAPACITY_SELECTABLE","placement_state":"WAITING_ARCHITECTURE_PROTECTION / WAITING_RUNTIME_PATH_RELEASE / needs_placement","cognition_route":"CHAT_INCLUDED_DEFAULT","chat_reasoning_mode":"NON_PRO_DEFAULT","worker_facing_commission_created":false,"implementation_branch_created":false,"implementation_started":false},"record_paths":["docs/superpowers/specs/2026-09-03-autonomy-closure-spine-v1-design.md","docs/superpowers/plans/2026-09-03-autonomy-closure-spine-v1.md","tests/test_autonomy_closure_spine_source_law.py"],"f0_stop_condition":"one current-base three-path Draft/HOLD PR with source-law proof, terminal hosted repository/security checks, and one independent exact-head review; no Runtime Event, worker, provider call, deployment, canary, or fleet promotion"}
```
<!-- AUTONOMY_CLOSURE_SPINE_V1_CONTRACT_END -->

## 16. Exact next action

Protect this F0 source after exact-head tests and independent review. Then keep ACF-1 held until C2-R1A releases the Runtime path; perform a fresh collision census and create one separately commissioned, capacity-placed ACF-1 child.