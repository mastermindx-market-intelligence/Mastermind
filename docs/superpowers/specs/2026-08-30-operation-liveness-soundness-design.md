# Mastermind Operation Liveness & Soundness — Architecture Freeze

**Date:** 2026-08-31  
**Owner:** Sol, AI CEO of Mastermind-X  
**Chairman:** Chris  
**Operation:** `mastermind-operation-liveness-soundness-20260830-sol-001`  
**Original research basis:** `Mastermind@28d365cceaef6efb0a26e0ac9af51ead44695d60`  
**Current protected reconciliation:** `Mastermind@990b5b6c10ca9acb2f5fa42405c688c3b2abe2fc`  
**Capability state:** `SPEC_ONLY / RECORDS_ONLY / PRODUCTION_INERT` until F0 protection

## CONTROLLING OLS-A1 IMPLEMENTATION NOTICE

Earlier architecture and plan examples preserve useful reasoning but contain historical drafting
residue. A fresh implementer must **do not implement** any older example that conflicts with these
sources, read in exact precedence order:

1. `docs/superpowers/specs/2026-08-30-operation-assurance-immutable-report-projection-clarification.md`
2. `docs/superpowers/specs/2026-08-30-operation-assurance-model-fidelity-counterexample-validation-amendment.md`
3. `docs/superpowers/specs/2026-08-30-operation-assurance-a1-trusted-input-total-proof-clarification.md`
4. `docs/superpowers/specs/2026-08-30-operation-assurance-a1-controlling-execution-overlay.md`

Adjacent source boundaries:

- `docs/superpowers/specs/2026-08-31-operation-liveness-soundness-executive-steward-reconciliation.md`
- `docs/superpowers/specs/2026-08-31-operation-liveness-soundness-sol-capability-fabric-reconciliation.md`
- `docs/superpowers/specs/2026-08-30-operation-liveness-soundness-runtime-observability-reconciliation.md`

This document freezes product, data, intelligence, and authority architecture. The executable task
contract is the current plan plus the precedence stack above.

## 1. Executive thesis

Mastermind already has strong local safety owners: Executive OS lifecycle, Agent OS responsibility,
Dialogue/Wake continuity, RuntimeBinding identity, Capacity placement, effect-unknown refusal, and
parent continuation. The missing capability is composed reasoning:

> Can an operation enter a reachable state where every local component behaves according to its own
> rules, yet the organization can no longer complete, resume, reconcile, or escalate?

Operation Assurance turns that question into a deterministic, explainable, source-attributed finite
analysis. Its value is not a decorative graph or another compliance checklist. Its value is enabling
larger autonomous programs without making Chairman intervention the hidden recovery mechanism.

## 2. Product thesis and value model

### 2.1 Primary user job

A Program CEO needs to understand whether a proposed or running operation has a reachable black hole,
why it exists, and the smallest owner-level repair that restores a lawful progress path.

### 2.2 Machine job

Compile one closed operation model, validate it exactly, explore every reachable state within
published limits, evaluate mandatory safety/workflow/liveness properties, and return one deterministic
minimal witness for every failed property.

### 2.3 Research and signal value

The growing asset is a corpus of source-attributed organizational failure traces, valid waits,
repairs, and forward outcomes. This supports calibration of model fidelity, false-positive/negative
rates, state-space growth, and which source contracts most often cause cross-seam failure.

### 2.4 Commercial and operational value

The capability reduces Chairman rescue work, makes autonomy expansion auditable, and creates a
credible safety story for larger multi-agent programs without hiding uncertainty behind model prose.

### 2.5 Data moat

The moat is first-party operational structure and correction history: exact owners, transitions,
assumptions, counterexamples, repairs, and observed outcomes. Provenance supports the intelligence;
it does not replace the useful explanation and repair workflow.

## 3. Research synthesis

### 3.1 Workflow-net soundness

Workflow-net research contributes three indispensable questions:

1. does every relevant reachable state retain an option to complete;
2. does completion leave only intended residue;
3. is every declared transition reachable when it is claimed usable?

Classical soundness does not directly cover Mastermind's external authority, correction, provider
binding, ambiguous effects, recurring services, or arbitrary data. It is therefore a property family,
not the canonical product model.

### 3.2 Temporal model checking

Temporal-logic practice separates safety from liveness and makes fairness assumptions explicit.
Explicit-state model checking provides deterministic reachability, strongly connected components,
and prefix + cycle counterexamples. These concepts map directly to Mastermind's ownerless states,
stranded parents, non-progress loops, and starvation.

### 3.3 Petri nets and graph linting

Petri-net projections may later provide independent concurrency diagnostics. Static graph linting is
useful for missing references and impossible topology. Neither can by itself establish the reachable
behavior of the full finite model.

### 3.4 External formal backends

TLA+, SPIN, Alloy, Apalache, SMT, or another reviewed backend may later audit selected models. None is
a V1 runtime dependency, source compiler, or authority owner. The Mastermind wire remains stable even
if an independent verifier is added.

### 3.5 Decidability boundary

Arbitrary workflows with unbounded creation, queues, clocks, opaque provider behavior, cancellation,
priority, or free-form human action cannot receive an honest universal liveness proof. The product
therefore uses a deliberately closed finite language and returns bounded or inconclusive outcomes
when the abstraction is incomplete.

## 4. Accepted system architecture

```text
canonical owner facts or authored fixture
        |
        v
mastermind.operation_assurance_model.v1
        |
        +--> exact parser and cross-reference validation
        +--> deterministic reachable-state graph
        +--> safety and workflow soundness
        +--> cyclic-SCC and fairness-product analysis
        +--> recurring progress and starvation
        v
mastermind.operation_assurance_report.v1
        |
        +--> report-only CLI in A1
        +--> current-status composition after A2/A3
        +--> Control Room explanation after A3
```

A1 is pure authored-input analysis. A2 later compiles source-attributed models through existing
owners. A3 joins immutable reports to current applicability in existing read/product surfaces.

## 5. Model architecture

### 5.1 Closed top-level shape

```text
schema
model_id
operation_ref
compiler
source_snapshot
abstraction_contract
state_domains
initial_state
transitions
terminal_outcomes
recurring_progress_outcomes
obligations
resources
external_gates
fairness_assumptions
environment_assumptions
safety_properties
property_set
exploration_limits
known_model_gaps
```

The schema is `mastermind.operation_assurance_model.v1`; the mandatory property set is
`mastermind.operation_assurance.properties.v1`.

### 5.2 State representation

Each variable has a finite non-empty closed domain. A state is an immutable tuple ordered by lexical
variable ID. The state fingerprint is a canonical SHA-256 digest over the variable/value map.

No arbitrary object graph, Python value, NaN, Infinity, bytes, regex, executable guard, or implicit
unbounded value enters the model.

### 5.3 Transition representation

Each transition has:

```text
transition_id
kind
actor_class
authority_requirement
guards
effects
progress_tags
source_refs
fairness_ref|null
external_assumption_ref|null
required_reachable
```

Guards use only reviewed equality/membership operations. Effects are simultaneous assignments.
Duplicate assignment to one variable is refused. Actor and authority labels are model facts, never
runtime grants.

### 5.4 Outcomes

Terminal outcomes represent accepted finite execution completion. Recurring outcomes represent
observable repeated service progress. Every outcome declares which persistent obligations or
resources it may lawfully own. Terminal outcomes cannot legalize non-persistent residue.

### 5.5 Obligations and resources

An obligation identifies its state variable, pending/discharged values, persistence, owner semantics,
and source refs. A resource identifies its holder variable, released values, persistence, and source
refs. The checker evaluates proper completion and starvation from these first-class objects.

### 5.6 Gates and waits

A gate or intentional wait binds state guards, owner or authority, machine-observable release
condition, explicit release transitions, observation source, Wake/review path, time contract,
correction contract, and escalation or closure transition. Prose alone never creates a valid wait.

### 5.7 Source snapshot

Every source reference binds owner, kind, identity, exact revision, schema, digest, coverage,
freshness, observation/effective time where owned, and correction reference. A source snapshot hash is
canonical and immutable.

## 6. Abstraction and evidence architecture

The model's required `abstraction_contract` states:

```text
kind
concrete_scope
preserves
introduced_behavior
excluded_behavior
validation_kind
validation_refs
notes
```

A declared-exact authored model can support a finite-model claim only about that model. A sound
over-approximation can support absence-of-violation for explicitly preserved properties but may
produce spurious witnesses. A trace-backed under-approximation can validate observed witnesses but
cannot prove universal absence. Heuristic or unknown fidelity remains diagnostic.

In OLS-A1, authored validation labels have zero trusted-evidence authority. The invocation boundary
is fixed to `AUTHORED_INPUT`; positive applicability is capped at `AUTHOR_DECLARED_ONLY`, and a
witness is at most `DECLARED_MODEL_ONLY` unless fidelity makes it potentially spurious.

A future compiler or replay validator must supply unforgeable typed host-owned receipts rather than
trust fields embedded in the model document.

## 7. Checker architecture

### 7.1 Parse and refusal boundary

The parser validates exact keys, types, IDs, domains, references, outcome ownership, gate closure,
fairness links, assumption links, and exploration bounds. Malformed wire receives no assurance
report.

### 7.2 Reachability

Breadth-first exploration discovers each state once, records canonical predecessor information, and
orders enabled transitions by transition ID. It records states discovered, transitions considered,
maximum depth, and peak frontier.

### 7.3 Safety

State-forbidden and transition-forbidden properties produce shortest prefixes. Mandatory built-ins
cover identity/authority, effect-unknown escape, terminal absorption, and other frozen invariants.

### 7.4 Option to complete

Reverse graph analysis marks states that can reach a terminal outcome, accepted recurring outcome,
valid gate/wait, or another property-specific accepted boundary. A state with no accepted path is a
workflow-soundness failure.

### 7.5 Proper completion

Every reached terminal outcome is checked for non-persistent obligations, held resources, live
children, open carrier turns, ambiguous effects, and parent-continuation residue represented in the
model.

### 7.6 Dead transitions

Every transition marked `required_reachable` must occur on at least one reachable edge. Absence is a
separate property result, not folded into liveness.

### 7.7 Terminal absorption

For every reached terminal state, the checker evaluates `NO_POST_TERMINAL_TRANSITION`. Any enabled
operation transition is a concrete counterexample. Logical stuttering is not an operation action.

### 7.8 Cyclic behavior

Tarjan or Kosaraju SCC analysis covers all reachable cyclic SCCs, including components with outgoing
completion edges. Liveness is not restricted to closed components because an execution may choose a
non-progress cycle indefinitely.

### 7.9 Weak-fair closed-walk product

For each candidate violating entry state, deterministic BFS explores:

```text
(graph_state, seen_or_disabled_fairness_mask, violation_progress_mask)
```

A return to the entry is accepted only when every named weak-fair transition was taken or disabled in
at least one visited cycle state and the property-specific non-progress condition remains true. This
allows a valid lasso to combine multiple simple cycles.

### 7.10 Fairness realizability

A declared weak-fair transition must be structurally and semantically capable of the service promise
used by a proof. Unreachable, contradictory, or vacuous fairness cannot remove all violating runs.
Strong fairness remains outside OLS-A1.

### 7.11 Recurring progress and starvation

Recurring progress requires a reached named recurring outcome or other exact reviewed evidence—not a
free-form progress tag. Persistent obligations are checked for fairness-valid lassos in which they
remain pending forever without accepted recurring progress.

### 7.12 Total completion

The base graph, reverse completion, safety checks, proper completion, dead-transition analysis, SCC
discovery, each fairness product, recurring analysis, and starvation search each expose completion.
No global proof is legal if any load-bearing analysis is incomplete.

## 8. Counterexample architecture

Every failed property receives one deterministic minimal witness containing:

```text
counterexample_id
property_id
model_hash
source_snapshot_hash
realizability
validation_refs
invalidating_gap_ids
shortest_prefix
cycle
state_delta_per_step
enabled_and_disabled_transition_reasons
source_refs
minimal deterministic repair candidates
limitations
```

Safety witnesses minimize prefix length. Liveness witnesses minimize prefix + cycle length, then
canonical transition sequence, then state fingerprint. Every step names the exact state delta and
source refs. Disabled-transition explanations distinguish absent authority, failed guard, held
resource, missing binding, source uncertainty, gate state, and other closed causes.

Repair candidates are deterministic descriptions of which model/source contract must change. They
are not executable actions or authority grants.

## 9. Report architecture

`mastermind.operation_assurance_report.v1` contains generation-time evidence only:

```text
schema
report_id
model_id
model_hash
source_snapshot_hash
checker_version
property_set_version
model_analysis_verdict
source_applicability_at_generation
abstraction_contract
progress_disposition
admission_recommendation
property_results
counterexamples
coverage
assumptions
known_model_gaps
exploration_receipt
generated_at
supersedes_report_id
report_hash
```

Report hash excludes `report_id` and `report_hash`; `report_id` derives from the hash. Fixed model and
fixed generated-at produce byte-identical output. Wall-clock duration is separate diagnostic data and
never enters canonical identity.

The immutable report never contains current status, current source receipts, current recommendation,
or recomputation time. Those belong to later existing-owner read composition.

## 10. Experience architecture

### 10.1 Control Room composition

The eventual card joins without conflating:

```text
canonical operation state
+ immutable assurance report
+ current source applicability and supersession
+ source-owned GitHub release/effect status
+ bounded diagnostic evidence
```

The headline names the model verdict and evidence scope, for example:

```text
UNSAFE_COUNTEREXAMPLE — SOURCE_CONTRACT_VALIDATED
MODEL COUNTEREXAMPLE — POTENTIALLY_SPURIOUS / VALIDATION REQUIRED
PROVEN_WITHIN_FINITE_MODEL — AUTHOR_DECLARED_ONLY
```

### 10.2 Counterexample timeline

The user sees the shortest prefix, repeating cycle, exact owner/resource/effect/binding state per
step, why alternatives were disabled, and the smallest repair candidates. Clicking a step navigates
to source-native receipts rather than an assurance-owned copy.

### 10.3 Required states

- checking;
- parser refusal;
- finite-model proof;
- bounded no-counterexample;
- inconclusive model gap;
- source stale or conflicted;
- externally gated;
- intentional wait;
- recurring service;
- fairness conditional;
- unsafe counterexample;
- potentially spurious witness;
- superseded report;
- checker internal failure.

### 10.4 Failure experience

Unknown data is shown as unknown. Partial pagination, stale revisions, moved Git head, missing
RuntimeBinding, conflicting owner identity, absent Wake receipt, and unavailable diagnostics each
remain distinct. No other axis fills the gap.

## 11. Source, time, and correction architecture

There is no universal freshness TTL. Each source owner defines freshness and correction semantics.
A model binds exact revisions; observation time alone cannot make data current.

A source change after generation does not mutate the report. Current status becomes stale,
superseded, unavailable, or inconclusive until a new model/report is created. Historical evidence
remains auditable.

A correction can invalidate a witness without deleting it. The current projection points to the
superseding report or corrected source receipt.

## 12. Authority and no-rebuild boundaries

Operation Assurance never:

- creates or mutates Job, Attempt, Worker, Event, lease, fence, retry, or admission state;
- creates a queue, scheduler, watcher, carrier, source graph, cache, or report database;
- elects an action target, account, provider, host, branch writer, or credential;
- gathers directly from Executive OS, Agent OS, Slack, GitHub, RuntimeBinding, or observability stores
  inside A1;
- performs a GitHub action, effect reconciliation, rerun, merge, or release;
- treats a model verdict as current operational authority;
- ranks executive demand.

Executive OS, Agent OS, Dialogue/Wake, RuntimeBinding, Capacity, Steward, SCF, Runtime Observability,
Project Workroom, GitHub, and Control Room remain the respective owners described in the law.

## 13. Adjacent-program reconciliation

- PR #228 is protected as a pure read core. It satisfies only the composition-core predecessor; A2
  still needs accepted A1 and a bounded gather/source compiler. Operation Assurance must not build a
  parallel federated reader.
- PR #268 remains watcher hardening and supplies a hostile self-deadlock case. It grants no OLS
  lifecycle or release authority.
- Executive Attention Frontier may consume serviceability reasons; Operation Assurance never ranks.
- Sol Capability Fabric owns GitHub status, release assessment, prepared actions, action receipts,
  and runner status. GitHub eligibility and OLS liveness are orthogonal.
- Runtime Observability owns diagnostic evidence. A complete trace is not proof of liveness; a missing
  trace is not proof of deadlock.
- Project Workroom and Worker Browser are product/collaboration surfaces, not assurance truth owners.

## 14. Vertical wave architecture

### OLS-F0

Records-only architecture and exact implementation contract.

### OLS-A1

One independently useful machine capability:

```text
real authored model -> deterministic checker -> immutable report -> real CLI consumer -> tests
```

### OLS-A2

One source-attributed compiler vertical after A1, using protected Steward and a separately accepted
bounded gather seam. It compiles one real operation, not the whole estate.

### OLS-A3

One Control Room read/explanation vertical with immutable/current separation and all failure states.

### OLS-A4/A5

Historical calibration followed by a prospective report-only canary. A canary must change a repair or
admission recommendation while all actual effects remain owned elsewhere.

### OLS-A6/G1

Runtime conformance and any later narrowly justified promotion. Enforcement is not inferred from
architecture, CI, or one canary.

## 15. Acceptance ruler

F0 is accepted when the exact source contract is internally consistent, current protected paths are
preserved, exact-head CI is green, direct Program-CEO adversarial review finds no blocker, and release
uses the expected head.

A1 is accepted only when hostile fixtures demonstrate safe finite proof, bounded honesty, model gaps,
effect-unknown escape detection, ownerless state detection, fair-lasso behavior, valid capacity wait,
valid Chairman gate, recurring progress, terminal absorption, and deterministic byte identity.

The full program is accepted only when:

- **Truth:** current source compilation is exact, correction-safe, rights-safe, and fail-closed;
- **Intelligence:** counterexamples and repairs are deterministic, minimal, and useful;
- **Product:** the Control Room supports the complete workflow across real and failure states;
- **Learning:** historical and prospective evidence shows whether the capability reduces rescue work
  and improves safe autonomous expansion.

Green CI is necessary evidence, never the product acceptance test.
