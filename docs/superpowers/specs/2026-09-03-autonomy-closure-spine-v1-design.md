# Autonomy Closure Spine v1 — Architecture Freeze

**Date:** 2026-09-03  
**Owner:** Sol, AI CEO of Mastermind-X  
**Chairman:** Chris  
**Operation:** `autonomy-closure-spine-f0-20260903-sol-001`  
**Canonical Git carrier:** Mastermind issue #437  
**Parent incident:** Mastermind issue #386  
**Protected source and procedure at pickup:** `mastermindx-market-intelligence/Mastermind@7022e70640637a4fa07f073442dc693301290e2a`, `mastermind.sol_skillpack.v1` 1.0.1, bootstrap-major 1  
**Capability state:** `SPEC_ONLY / RECORDS_ONLY / PRODUCTION_INERT`  
**Effect:** no Runtime, Job, Attempt, Worker, Event, provider, Wake, RuntimeBinding, deployment, production or fleet effect

This is a **records-only** architecture freeze. It creates no implementation branch, no worker assignment, and **no implementation START**. Source protection is not production proof.

## 1. Executive ruling

Mastermind already has the correct primary autonomy owners: Executive Runtime, Agent OS, Capacity, RuntimeBinding, Wake, Agent Relay, Agent Dialogue, the COO cycle, Control Room and GitHub. The company does not need another autonomy platform.

It does need one missing convergence contract.

The exact action-target path answers:

> Which Sol surface is currently permitted to act for this root?

The dialogue path answers:

> Which instructions and returns were transported?

Neither currently answers, atomically and machine-authoritatively:

> Which one semantic decision is effective for this exact terminal return, under this exact action-target generation, and which downstream transition consumed it?

That gap can leave the system technically well-instrumented but operationally split-brain. Two Sols may observe the same return; an old Sol may revive after rotation; a Chairman correction may supersede an earlier ruling; a transport may deliver text before or after the corresponding Runtime effect. Without one canonical decision Event, procedure and timestamp ordering must reconstruct precedence after the fact.

The selected repair is **Autonomy Closure Spine v1**: a thin set of missing contracts inside the existing owners. Only its first layer, ACF-1 Semantic Directive Convergence, is permitted before the first fleet. ACF-2 through ACF-6 are evidence-gated follow-ons and remain held.

## 2. Why this is the permitted architecture exception

Protected `Autonomy Completion Mode` correctly defaults to `NO_NEW_AUTONOMY_ARCHITECTURE`. The exception requires a concrete missing owner/contract and a named golden-path edge.

This architecture satisfies that test:

```text
concrete blocker:
exact action target exists
but no Runtime-owned semantic decision compare-and-swap exists

edge unlocked:
terminal return
-> exact Sol attention
-> one effective decision
-> one next same-root transition
```

The defect has already appeared in live operating evidence:

- the W3C carrier accumulated conflicting action-looking 14-, 16-, 19- and 25-path rulings before a later Chairman correction established precedence;
- the C2 carrier received a stale retreat after valid `START_RESUMED` and required a later Chairman correction;
- issue #400 attempted to duplicate the broader dispatch incident and was correctly closed as a duplicate of #386.

The new contract is therefore not speculative generalized infrastructure. It closes the explicit `two Sol observers` adversarial case already required by completion mode.

## 3. Ten-out-of-ten operating outcome

The target journey is:

```text
one exact terminal worker return
-> W3C / Wake delivers attention
-> multiple Sol surfaces may observe
-> Stage B / RuntimeBinding identifies one current action target
-> Executive Runtime commits one effective semantic directive
-> exact replay is idempotent
-> stale and observer directives are refused with zero effect
-> existing COO cycle consumes that Event once
-> one lawful next transition occurs
-> Control Room explains current decision, consumption and conflicts
-> zero Chairman message shuttle
```

A Slack message, visible model response, watcher wake, browser foreground action, delivery receipt, pickup acknowledgement or action-target resolution is not itself the effective semantic decision.

## 4. Current estate and collision map

### Protected and consumed

- W3C-I1 source is protected through PR #427 / merge `a945e76befb34d15d0ab0e369b4197901883bb16`.
- Stage-B V6.1 is protected and remains the exact target-assignment owner.
- Stage A remains the storeless current-target and exact-actor enforcement owner.
- terminal-return, retry-safety, COO-cycle, Runtime Event, SessionTarget and RuntimeBinding primitives are protected source and must be reused.

### Active and exclusive

- C2-R1A PR #415 remains the active `control_plane/executive_runtime.py` writer. ACF-1 runtime implementation must not collide with it.
- Control Room PR #326 remains the active projection/UI owner. ACF-1 must not edit its paths until that carrier protects or explicitly releases them.
- MAT-S1 issue #430 remains predecessor-held; it will materialize the role-null CEO carrier and establish the current writer read required by Stage-B1.
- issue #386 remains the canonical dispatch-consumption incident and final end-to-end acceptance carrier.

### Held

- ACF-1 implementation is `WAITING_ARCHITECTURE_PROTECTION / WAITING_RUNTIME_PATH_RELEASE / needs_placement`.
- ACF-2 through ACF-6 receive no implementation authority from this architecture.

## 5. Three truths that must remain separate

### Target truth

Owned by SessionTargetRegistry, RuntimeBinding and Stage B. It establishes the one current Sol target and binding generation.

### Transport truth

Owned by Wake, W3C, Agent Relay and Agent Dialogue. It establishes what was delivered, acknowledged, read, returned and rendered.

### Decision truth

Owned by the existing Executive Runtime Event plane. It establishes the one effective semantic directive and its downstream consumption.

A transport can succeed while a Runtime commit fails. A Runtime commit can succeed while a response is lost. A current target can exist without any decision. A decision can be committed but not yet consumed. These states must never be collapsed.

## 6. Semantic directive contract

The first implementation vertical extends the existing Event plane with:

```text
command schema: mastermind.executive_semantic_directive_command/v1
event schema:   mastermind.executive_semantic_directive/v1
event type:     EXECUTIVE_SEMANTIC_DIRECTIVE_COMMITTED
```

The schema binds one return, one target generation, one actor, one decision revision and one payload digest. It carries no raw model or transport content.

### Decision enum

```text
CONTINUE
REPAIR
STOP
ESCALATE
```

These values are deliberately organizational semantics rather than arbitrary commands.

- `CONTINUE` allows only the next transition already lawful under the existing root plan and authority.
- `REPAIR` allows only an existing bounded repair path.
- `STOP` closes the current reciprocal child wave and does not originate a successor.
- `ESCALATE` records a typed gate and performs no hidden action.

### Actor classes

```text
ACTION_TARGET
CHAIRMAN
```

An observer, sibling Sol, Slack identity, model name, browser account nickname, newest tab or transport sender is not an actor class with directive authority.

## 7. Runtime compare-and-swap law

The Runtime commit must re-read current canonical facts in one existing transaction. A previously generated target-resolution object is evidence only and never a reusable capability.

The commit compares:

```text
root identity
source Job / Attempt / Worker
terminal-return Event and digest
current target alias / binding / generation / surface
actor identity receipt
predecessor directive identity and revision
semantic decision and payload digest
```

Required results:

- exact replay with current evidence returns the same Event;
- changed semantic payload under the same command identity is `COMMAND_REPLAY_CONFLICT`;
- an observer Sol is a typed zero-effect refusal;
- an old binding generation is a typed zero-effect refusal;
- a late result from a superseded Attempt is a typed zero-effect refusal;
- stale or changed terminal evidence is a typed zero-effect refusal;
- `CONTINUE` and `STOP` racing for one revision produce exactly one effective Event;
- a Chairman supersession creates a new explicit revision preserving history;
- timestamp or Slack message order alone never supersedes;
- response loss after Runtime commit is reconciled by Event readback and never repeats the commit;
- successful transport without a Runtime Event creates no effective directive.

## 8. Consumer law

The existing COO cycle is the first machine consumer. It may consume only the current effective directive Event and never parse Slack prose to decide the next mutation.

The downstream command must bind the directive Event identity and digest. Exact replay after restart may reconstruct the already-consumed state but may not perform the mutation twice.

The directive does not itself:

- start a provider process;
- create another Job or Attempt outside current orchestration law;
- retry an uncertain effect;
- merge a PR;
- deploy production;
- mark a root accepted;
- grant new authority.

## 9. Correction and supersession

Directive history is immutable.

A correction does not rewrite an older directive. It creates a new revision with:

```text
predecessor_directive_id
supersedes_directive_id
current target or Chairman authority receipt
new decision payload digest
```

Only a current Chairman receipt may supersede a still-valid action-target decision from outside the ordinary target path. A normal target rotation does not silently rewrite an effective historical decision; it changes which actor may commit the next revision.

## 10. Time and freshness

Wall-clock recency does not elect precedence.

`created_at` is recorded for audit and ordering, but effectiveness derives from exact causal identities and revisions. Freshness comes from re-reading the terminal return, target generation, actor identity and predecessor revision at the transaction boundary.

Clock skew cannot make an old target current or a later Slack post effective.

## 11. Effect uncertainty

The Runtime commit is local and command-idempotent. The transport that asks for it may still lose a response.

```text
request definitely not submitted -> safe no-effect
Runtime Event found by exact command -> APPLIED
Runtime Event absent after proven no-submit -> NOT_APPLIED
submission may have crossed boundary and readback unavailable -> EFFECT_UNKNOWN
```

`EFFECT_UNKNOWN` blocks another directive request, alternate target, carrier failover or fallback transport until the same owner reconciles it.

## 12. Control Room projection

After the active Control Room carrier releases its paths, the existing Control Room may project:

```text
AWAITING_SEMANTIC_DIRECTIVE
DIRECTIVE_COMMITTED
DIRECTIVE_CONSUMED
STALE_DIRECTIVE_REJECTED
CONFLICTING_DIRECTIVE_REJECTED
CHAIRMAN_SUPERSEDED
DIRECTIVE_EFFECT_UNKNOWN
```

The projection remains read-only. Missing projection does not stop Runtime; a healthy-looking projection cannot authorize a decision.

## 13. Follow-on closure layers

Only ACF-1 is authorized before first-fleet proof.

### ACF-2 — mission-envelope enforcement

Start only if the golden-root canary proves that current DelegationPacket fields are not enforced through admission and accounting. Reuse the existing packet and Executive admission owner.

### ACF-3 — useful progress versus heartbeat

Start only if the explicit stall falsifier cannot be represented through existing Attempt/checkpoint/Event semantics. Heartbeat is not automatically useful progress, but the system must not create a parallel monitoring lifecycle merely to express that distinction.

### ACF-4 — truthful production acceptance

Start after one real golden-root result exists and only if current production-proof owners cannot express the accepted capability without conflating CI, merge, terminal state or Slack RESULT.

### ACF-5 — resource finalization

Start only from concrete installed resources exposed by the golden root. Finalization extends each resource's existing owner; it does not create a universal resource manager.

### ACF-6 — compatibility receipt

Start only when an installed producer-consumer generation mismatch is reproduced. Extend current release and capability owners rather than creating a package registry.

## 14. Failure matrix for ACF-1

The implementation and production canary must include:

1. two observers and one current target;
2. old target revives after rotation;
3. current target exact replay;
4. changed payload under same command;
5. `CONTINUE` versus `STOP` transaction race;
6. stale source Attempt;
7. changed terminal return digest;
8. late superseded Attempt return;
9. explicit Chairman supersession;
10. lost response after commit;
11. Slack delivery with no Runtime commit;
12. process restart between directive commit and COO consumption;
13. duplicate consumer execution attempt;
14. unavailable Control Room projection;
15. provider/Slack/model prose attempting to manufacture authority.

Every case must converge to one closed, explainable state.

## 15. Implementation ownership and expected paths

After F0 source protection and C2 path release, the smallest expected ACF-1 surface is:

```text
control_plane/executive_semantic_directive.py
control_plane/executive_runtime.py
control_plane/executive_coo_cycle.py
control_plane/executive_service.py                 # only if an existing bounded request seam is required
new focused directive tests
existing Runtime / COO / service tests only where integrated
```

Action-time archaeology may shrink this list. A new path or owner collision returns to Sol before edit.

W3C, Wake, Relay, SessionTarget, Stage B, RuntimeBinding and Control Room source are consumers or prerequisites, not default ACF-1 edit surfaces.

## 16. Routing

```text
future operation: autonomy-semantic-directive-convergence-acf1-20260903-sol-001
PREFERRED_AVENUE: CTO Sol
WHY NOT FABLE: the Chairman outcome, owner map, event semantics, failure matrix, no-rebuild boundaries, and acceptance are frozen
RECEIVER_BINDING_MODE: CAPACITY_SELECTABLE
PLACEMENT_STATE: WAITING_ARCHITECTURE_PROTECTION / WAITING_RUNTIME_PATH_RELEASE / needs_placement
COGNITION_ROUTE: CHAT_INCLUDED_DEFAULT
CHAT_REASONING_MODE: NON_PRO_DEFAULT
```

This is not a worker-facing commission. No task, session, watcher, branch or implementation START exists.

## 17. Acceptance

F0 is complete only when its exact three-path source is protected after source-law tests, hosted repository/security proof and independent exact-head review.

ACF-1 source is complete only when the pure contract, Runtime commit, COO consumer and restart/idempotency behavior are one independently useful vertical. It remains `BUILT_NOT_PROVEN / DEFAULT_DISARMED` after merge.

Production acceptance requires one real terminal return observed by at least two Sol-capable surfaces, one current action target, one effective Runtime directive, one downstream transition and **zero Chairman message shuttle**.

No source document, issue, green CI, merge, Slack message or synthetic fixture can satisfy that production ruler.

## 18. Durable contract

<!-- AUTONOMY_CLOSURE_SPINE_V1_CONTRACT_BEGIN -->
```json
{"schema":"mastermind.autonomy_closure_spine.v1","operation":"autonomy-closure-spine-f0-20260903-sol-001","parent_incident":"Mastermind#386","closed_duplicate_not_owner":"Mastermind#400","protected_pickup":"7022e70640637a4fa07f073442dc693301290e2a","current_state":{"capability":"SPEC_ONLY / RECORDS_ONLY / PRODUCTION_INERT","implementation_started":false,"runtime_effect":false,"provider_effect":false,"production_armed":false,"worker_assigned":false},"architecture_exception":{"default_preserved":"NO_NEW_AUTONOMY_ARCHITECTURE","concrete_blocker":"the exact action-authoritative Sol target exists, but no Runtime-owned compare-and-swap semantic directive binds one exact return to one effective CONTINUE, REPAIR, STOP, or ESCALATE decision","golden_path_edge_unlocked":"terminal return -> exact Sol attention -> one effective Sol decision -> one next same-root transition","observed_incident_class":["conflicting W3C scope directives","stale C2 retreat after START_RESUMED"]},"authorized_pre_fleet_layers":["ACF-1"],"owners":{"lifecycle_and_atomic_commit":"Executive Runtime","current_sol_target":"SessionTargetRegistry / RuntimeBinding / Stage B","terminal_return":"existing Executive terminal-return owner","attention_delivery_ack":"Wake / W3C / Agent Relay","dialogue_transport":"Agent Dialogue","next_orchestration_mutation":"existing COO cycle","operational_projection":"existing Control Room","organizational_memory":"Agent OS","implementation_evidence":"GitHub"},"no_rebuild":{"new_lifecycles":[],"new_databases":[],"new_queues":[],"new_schedulers":[],"new_retry_planes":[],"new_watcher_registries":[],"new_runtime_binding_stores":[],"new_authority_registries":[],"new_transcript_stores":[],"new_control_room_truth_stores":[],"slack_as_runtime_authority":false},"acf1_semantic_directive_convergence":{"command_schema":"mastermind.executive_semantic_directive_command/v1","event_schema":"mastermind.executive_semantic_directive/v1","event_type":"EXECUTIVE_SEMANTIC_DIRECTIVE_COMMITTED","decisions":["CONTINUE","REPAIR","STOP","ESCALATE"],"actor_classes":["ACTION_TARGET","CHAIRMAN"],"required_fields":["directive_id","root_job_id","source_job_id","source_attempt_id","source_worker_id","consumed_terminal_event_id","consumed_terminal_event_digest","current_target_alias","current_target_binding_id","current_target_binding_generation","current_target_reasoning_surface","actor_class","actor_identity_receipt_digest","carrier_reference","predecessor_directive_id","revision","decision","decision_payload_digest","supersedes_directive_id","created_at"],"forbidden_fields":["prompt","model_output","transcript","arbitrary_slack_prose","credential","account_email","provider_secret","browser_content","raw_url","reusable_authority_token"],"commit_semantics":{"runtime_reresolves_current_target":true,"compare_root_return_target_generation_and_predecessor_revision":true,"one_effective_directive_per_return_revision":true,"exact_replay_is_idempotent_after_current_revalidation":true,"changed_payload_is_command_replay_conflict":true,"observer_sol_is_zero_effect_refusal":true,"stale_target_generation_is_zero_effect_refusal":true,"late_superseded_attempt_is_zero_effect_refusal":true,"chairman_supersession_is_explicit_and_history_preserving":true,"transport_loss_after_commit_uses_event_readback":true,"transport_success_without_runtime_commit_is_not_effective":true,"continue_and_stop_cannot_both_be_effective":true},"consumer":{"owner":"existing COO cycle","reads_slack_prose":false,"consumes_effective_event_once":true,"downstream_mutation_is_bound_to_directive_event":true,"directive_is_not_provider_start_retry_merge_or_deploy":true}},"conditional_follow_on_layers":{"ACF-2":{"name":"mission-envelope enforcement","start_gate":"post-golden-root evidence of admission/accounting gap","reuse_owner":"existing DelegationPacket and Executive admission"},"ACF-3":{"name":"useful-progress versus heartbeat","start_gate":"post-golden-root stall falsifier cannot close through checkpoints","reuse_owner":"existing Attempt checkpoint and Event plane"},"ACF-4":{"name":"truthful production acceptance","start_gate":"one real golden-root result exists","reuse_owner":"existing root Event and production-proof owners"},"ACF-5":{"name":"resource finalization","start_gate":"installed golden root exposes concrete required resources","reuse_owner":"the existing owner of each created resource"},"ACF-6":{"name":"producer-consumer compatibility receipt","start_gate":"an installed-generation incompatibility is reproduced","reuse_owner":"existing release and capability owners"}},"acf1_routing":{"future_operation_key":"autonomy-semantic-directive-convergence-acf1-20260903-sol-001","preferred_avenue":"CTO Sol","why_not_fable":"the Chairman outcome, owner map, event semantics, failure matrix, no-rebuild boundaries, and acceptance are frozen","receiver_binding_mode":"CAPACITY_SELECTABLE","placement_state":"WAITING_ARCHITECTURE_PROTECTION / WAITING_RUNTIME_PATH_RELEASE / needs_placement","cognition_route":"CHAT_INCLUDED_DEFAULT","chat_reasoning_mode":"NON_PRO_DEFAULT","worker_facing_commission_created":false,"implementation_branch_created":false,"implementation_started":false},"record_paths":["docs/superpowers/specs/2026-09-03-autonomy-closure-spine-v1-design.md","docs/superpowers/plans/2026-09-03-autonomy-closure-spine-v1.md","tests/test_autonomy_closure_spine_source_law.py"],"f0_stop_condition":"one current-base three-path Draft/HOLD PR with source-law proof, terminal hosted repository/security checks, and one independent exact-head review; no Runtime Event, worker, provider call, deployment, canary, or fleet promotion"}
```
<!-- AUTONOMY_CLOSURE_SPINE_V1_CONTRACT_END -->

## 19. Exact next action

Protect this three-path F0 source. Then keep ACF-1 waiting until C2-R1A releases `control_plane/executive_runtime.py`. A fresh Sol performs the current-source/path collision census and creates one separately commissioned ACF-1 child. The existing W3C/C2/MAT-S1/Stage-B1/Control Room train continues in parallel under its own current carriers.