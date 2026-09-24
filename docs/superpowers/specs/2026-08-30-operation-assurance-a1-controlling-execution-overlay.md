# Operation Assurance A1 — Controlling Execution Overlay

**Status:** CONTROLLING EXECUTION OVERLAY / SPEC_ONLY / RECORDS_ONLY / PRODUCTION_INERT  
**Date:** 2026-08-30  
**Owner:** Sol, AI CEO of Mastermind-X  
**Operation:** `mastermind-operation-liveness-soundness-20260830-sol-001`  
**Protected source reconciled:** `mastermindx-market-intelligence/Mastermind@620263090fb9f272f763e420ba103b0ff8dc5f31`  
**Parent law:** `docs/OPERATION_LIVENESS_SOUNDNESS_LAW.md`  
**Parent design:** `docs/superpowers/specs/2026-08-30-operation-liveness-soundness-design.md`  
**Parent implementation plan:** `docs/superpowers/plans/2026-08-30-operation-assurance-core.md`  
**Fidelity amendment:** `docs/superpowers/specs/2026-08-30-operation-assurance-model-fidelity-counterexample-validation-amendment.md`  
**Immutable-report clarification:** `docs/superpowers/specs/2026-08-30-operation-assurance-immutable-report-projection-clarification.md`

This document closes the remaining task-level precedence gap in OLS-F0. The parent architecture and
implementation plan were written before the model-fidelity amendment and immutable-report
clarification. Some early examples therefore still use withdrawn fields or obsolete verdict
composition. Those examples are historical drafting residue, not implementation authority.

The immutable-report clarification remains the highest wire-specific authority, followed by the
model-fidelity amendment. This overlay translates both into one executable OLS-A1 task contract.
Where this overlay conflicts with the parent law, design, or implementation plan, this overlay wins.
If this overlay conflicts with either named amendment, the amendments win.

This overlay changes no accepted system architecture. It adds no executable checker, runtime
integration, source compiler, admission behavior, Control Room surface, persistence, or authority.

## 1. Withdrawn parent-plan instructions

The following earlier instructions are superseded before OLS-A1 implementation:

1. A minimal model without `abstraction_contract` is not valid.
2. The immutable report field `assurance_verdict` is withdrawn.
3. `MODEL_STALE_OR_INVALID` is not an immutable model-analysis verdict.
4. The immutable fields `current_projection_verdict` and bare `source_applicability` are withdrawn.
5. Source staleness or conflict does not erase or replace the model-analysis result.
6. A blanket rule that every load-bearing gap outranks every concrete witness is withdrawn.
7. OLS-A1 cannot emit `REPORT_ONLY_PROCEED`.
8. A descriptive gate object without a modeled release, escalation, cancellation, review, lawful
   closure, or terminal assessment boundary is not a valid gate.
9. Liveness analysis is not limited to closed strongly connected components.
10. Strong fairness is not part of OLS-A1.

All later implementation commits, tests, fixtures, CLI output, reviews, and handoffs must use this
corrected contract from their first parser/report commit.

## 2. OLS-A1 capability and no-rebuild boundary

OLS-A1 remains a pure, deterministic, standard-library-only, report-only vertical slice:

```text
authored closed model
-> exact parser and cross-reference validation
-> deterministic finite-state exploration
-> safety, workflow-soundness, liveness, fairness, and starvation checks
-> minimal source-attributed counterexample
-> immutable mastermind.operation_assurance_report.v1
-> stdout through a bounded CLI
```

The model, checker, and report modules perform zero network, socket, subprocess, telemetry,
filesystem-write, SQLite, runtime, or source-owner I/O. The CLI may read the one explicitly supplied
model file or stdin and write one report to stdout; it owns no store and performs no runtime write.

No Executive OS, Agent OS, Wake, RuntimeBinding, Capacity, Steward, Control Room, watcher, retry, or
Runtime Observability mutation is permitted. OLS-A1 also creates no lifecycle, queue, scheduler,
carrier, authority registry, session registry, worker registry, capacity allocator, attention
allocator, retry/failover path, telemetry emitter, collector, sidecar, diagnostic backend, source
graph, or second Steward.

An unsafe authored model still produces a valid report and normal CLI completion. The CLI is not an
implicit admission gate. Malformed JSON or a refused closed model returns the bounded invalid-input
exit, but an unsafe model result itself does not.

## 3. Corrected closed model wire

`mastermind.operation_assurance_model.v1` is an immutable analysis value, never lifecycle or
authority truth. Its top-level fields are:

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

abstraction_contract is required.

Its exact fields are:

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

Closed abstraction kinds are:

```text
DECLARED_EXACT
SOUND_OVERAPPROXIMATION
TRACE_BACKED_UNDERAPPROXIMATION
HEURISTIC_ABSTRACTION
UNKNOWN_FIDELITY
```

Closed preservation claims are:

```text
SAFETY
REACHABLE_COUNTEREXAMPLE
OPTION_TO_COMPLETE
UNIVERSAL_PROGRESS
LIVENESS_UNDER_DECLARED_FAIRNESS
RESOURCE_OWNERSHIP
EFFECT_RETRY_SAFETY
```

Closed validation kinds are `AUTHOR_DECLARATION`, `SOURCE_COMPILER_ATTESTATION`,
`SOURCE_CONTRACT_REPLAY`, `RUNTIME_EVENT_REPLAY`, `INDEPENDENT_FORMAL_EQUIVALENCE`, and `NONE`.
OLS-A1-authored files normally use `AUTHOR_DECLARATION`; they cannot self-attest current production
applicability.

### 3.1 Transitions and properties

Every transition has a stable ID, closed guards and effects, actor class, authority requirement,
progress tags, source references, optional declared fairness reference, optional external-assumption
reference, and required-reachability flag. Arbitrary Python, shell, SQL, regular expressions, dynamic
imports, or model-generated executable predicates are forbidden.

The bidirectional reference law is fail-closed: transition fairness_ref and fairness assumption
transition_ids must agree exactly, and transition external_assumption_ref and environment assumption
transition_ids must agree exactly. A one-sided or mismatched reference is a parser error, not an
implicit assumption. Effects are simultaneous assignments, and duplicate effects for the same state
variable are rejected rather than ordered.

Safety properties have exactly one of two closed shapes:

- `STATE_FORBIDDEN` with `violation_when`;
- `TRANSITION_FORBIDDEN` with `when` and `forbidden_transition_kinds`.

Unknown keys, mixed shapes, missing references, non-finite domains, values outside their domains,
duplicate IDs, or opaque behavior fail closed during parsing.

### 3.2 Outcomes, obligations, and resources

Every terminal or recurring outcome contains:

```text
outcome_id
kind
guards
owned_persistent_obligation_ids
owned_persistent_resource_ids
source_refs
```

The required fields owned_persistent_obligation_ids and owned_persistent_resource_ids identify only
persistent residue explicitly owned by that outcome. A terminal outcome can never legalize
non-persistent pending obligations, held resources, unresolved effects, live children, open carrier
turns, or missing parent continuation.

### 3.3 Gates and waits

Every gate or intentional wait contains:

```text
gate_id
disposition
state_guards
owner_or_authority
release_condition
release_transition_ids
return_or_observation_source
wake_or_review_path
time_contract
correction_contract
escalation_or_close_path
source_refs
```

`release_transition_ids` must resolve to explicit model transitions that represent release, review,
escalation, cancellation, refusal, or lawful closure, unless the model declares an explicit terminal
assessment boundary. The controlling rule is exact: descriptive gate prose alone never legalizes a
dead state.

The structural and semantic boundaries remain distinct: a missing required gate field is parser
refusal; a syntactically complete gate without a realizable release or terminal assessment boundary
is EXTERNAL_GATE_INCOMPLETE and a load-bearing model gap.

An environment assumption has a stable ID, closed kind, transition IDs, required property IDs, and
source references. An external-event assumption does not create fairness and does not promise that a
human will act.

### 3.4 Fairness

NONE fairness is represented by absence of a fairness assumption. `WEAK` is the only admitted
fairness kind in OLS-A1 and applies only to named transitions continuously enabled throughout a
candidate cycle. STRONG fairness is rejected in OLS-A1.

### 3.5 Model gaps

Every model gap contains:

```text
gap_id
reason
load_bearing
affects_property_ids
affects_transition_ids
affects_variable_ids
source_refs
```

The parser resolves every affected identity. Empty `affects_*` arrays are permitted only for a
non-load-bearing gap whose reason explains why it cannot alter any checked property.

## 4. Corrected immutable report wire

`mastermind.operation_assurance_report.v1` is content-addressed historical evidence for one checker
run. It contains generation-time facts only:

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

`progress_disposition` and `admission_recommendation` are immutable generation-time findings. They do
not claim current applicability and never mutate the model-analysis result.

Report identity has no circular dependency. report_hash is computed from the canonical report body
excluding report_id and report_hash. report_id is oar_ plus the first 24 hexadecimal characters of
report_hash. Both are then serialized into the final immutable report. The exploration receipt uses
deterministic work counts such as states discovered, transitions considered, maximum depth, and peak
frontier. duration_ms is excluded from the OLS-A1 canonical report because wall-clock timing would
break byte-identical output for a fixed model and generated_at; performance timing may be separate
non-authoritative diagnostic evidence.

model_analysis_verdict has exactly four values:

```text
UNSAFE_COUNTEREXAMPLE
PROVEN_WITHIN_FINITE_MODEL
BOUNDED_NO_COUNTEREXAMPLE
INCONCLUSIVE_MODEL_GAP
```

Generation-time source applicability has these closed values:

```text
AUTHOR_DECLARED_ONLY
CURRENT_SOURCE_ATTESTED
HISTORICAL_SOURCE_ATTESTED
STALE
CONFLICTED
INCOMPLETE
UNKNOWN
```

The controlling withdrawal rules are:

- MODEL_STALE_OR_INVALID is a current derived status, not a model-analysis verdict.
- current_projection_verdict is withdrawn from the immutable report.
- the ambiguous bare source_applicability field is withdrawn.
- the immutable field is `source_applicability_at_generation`.
- changing a later current source receipt never mutates or re-hashes an old report.

OLS-A1 never emits mastermind.operation_assurance_status.v1. That later current status is a
non-persisted or existing-owner-cached read composition in corrected Steward / Control Room after
OLS-A2/A3. It owns no report mutation, recheck scheduler, admission, retry, or source correction.

## 5. Counterexample contract and certainty

Every counterexample contains at least:

```text
counterexample_id
property_id
realizability
validation_refs
invalidating_gap_ids
shortest_prefix
cycle
state_delta_per_step
enabled_and_disabled_transition_reasons
source_refs
repair_candidates
limitations
```

Closed realizability values are:

```text
DECLARED_MODEL_ONLY
SOURCE_CONTRACT_VALIDATED
RUNTIME_REPLAY_CONFIRMED
POTENTIALLY_SPURIOUS
INVALIDATED
```

A checker witness starts as `DECLARED_MODEL_ONLY` unless a separately accepted deterministic source
validator or canonical semantic-event replay supplies stronger receipts. Runtime diagnostic
evidence may enrich a replay, but telemetry alone cannot create RUNTIME_REPLAY_CONFIRMED.

Counterexample certainty uses trace/property-specific relevance:

- an unrelated non-load-bearing gap does not hide a definite witness;
- a relevant load-bearing gap weakens witness certainty;
- a `DECLARED_EXACT` authored model may report `UNSAFE_COUNTEREXAMPLE` within the declared model;
- an over-approximate, heuristic, unknown-fidelity, or relevant-gap witness is
  `POTENTIALLY_SPURIOUS` and normally yields `INCONCLUSIVE_MODEL_GAP`;
- a failed validation or conflicting correction can mark a historical witness `INVALIDATED` without
  deleting it.

## 6. Verdict, applicability, disposition, and recommendation composition

The checker computes independent axes in this order.

### 6.1 Parser boundary

Malformed schema, unknown fields, unresolved references, non-finite domains, unsupported guard or
fairness semantics, or invalid canonical JSON cause parser refusal. No assurance report is emitted.

### 6.2 Model-analysis verdict

Model analysis is composed without overwriting it with source applicability:

1. A realizable witness with no relevant invalidating gap yields `UNSAFE_COUNTEREXAMPLE`.
2. A declared-exact authored witness with no relevant invalidating gap yields
   `UNSAFE_COUNTEREXAMPLE` within the declared model.
3. A potentially spurious witness, unknown fidelity, or relevant load-bearing gap yields
   `INCONCLUSIVE_MODEL_GAP`, while retaining the candidate witness and limitations.
4. Complete reachable-state exploration, all required properties known and passing, a
   property-preserving abstraction, finite declared domains, and normal checker completion yield
   `PROVEN_WITHIN_FINITE_MODEL`.
5. Incomplete exploration with no witness yields `BOUNDED_NO_COUNTEREXAMPLE`.
6. Every remaining case yields `INCONCLUSIVE_MODEL_GAP`.

A state or depth limit, checker exception, unsupported construct, unknown relevant fact, or
under-approximate absence of a witness can never become proof.

### 6.3 Source applicability at generation

OLS-A1-authored fixtures use `AUTHOR_DECLARED_ONLY` unless a negative fixture explicitly carries
stale, conflicted, incomplete, or unknown source receipts. Only a later protected canonical source
compiler may assert `CURRENT_SOURCE_ATTESTED` or `HISTORICAL_SOURCE_ATTESTED`.

A stale or conflicted source receipt preserves the model-analysis result and separately records
`STALE` or `CONFLICTED`. It forces the generation-time recommendation to
`REPORT_ONLY_RECONCILE`; it does not rewrite the report’s model verdict.

### 6.4 Progress disposition

Disposition is selected only from reached matching states and failed progress properties, using:

```text
NO_PROGRESS
EXTERNALLY_GATED
INTENTIONAL_WAIT
RECURRING_SERVICE
FAIRNESS_CONDITIONAL
AUTONOMOUSLY_LIVE
UNKNOWN
```

`NO_PROGRESS` requires a concrete failed progress property. A gate, wait, or recurring disposition
never upgrades a bounded or inconclusive model verdict.

### 6.5 Report-only recommendation

OLS-A1 never emits REPORT_ONLY_PROCEED.

The closed A1 recommendation law is:

- stale or conflicted generation-time source basis -> `REPORT_ONLY_RECONCILE`;
- declared-exact model-only unsafe witness -> `REPORT_ONLY_REPAIR`;
- source-validated or runtime-replayed unsafe witness in a later eligible context ->
  `REPORT_ONLY_REPAIR`;
- potentially spurious witness -> `REPORT_ONLY_NO_RECOMMENDATION`;
- complete declared gate or wait -> `REPORT_ONLY_AWAIT_GATE`;
- finite-model proof with `AUTHOR_DECLARED_ONLY` -> `REPORT_ONLY_NO_RECOMMENDATION`;
- bounded no-counterexample -> `REPORT_ONLY_NO_RECOMMENDATION`;
- inconclusive or incomplete -> `REPORT_ONLY_NO_RECOMMENDATION`.

`REPORT_ONLY_PROCEED` first becomes eligible only after a protected source compiler attests a current
property-preserving model and a separately accepted report-only policy permits that exact class.

## 7. Corrected liveness and waiting semantics

OLS-A1 analyzes all reachable cyclic SCCs and candidate obligation-preserving cycles, not only closed
SCCs. A cycle may be a valid infinite non-progress execution even when its component has an outgoing
completion edge, unless declared weak fairness excludes that exact lasso.

The witness search is over a fairness-valid closed walk, not only a simple cycle. A valid ultimately
periodic execution may combine multiple simple cycles to take different weak-fair transitions while
still preserving the violating obligation. For each candidate entry, deterministic BFS runs over an
augmented state `(graph_state, seen_or_disabled_fairness_mask, violation_progress_mask)`. The
seen-or-disabled fairness mask records, for each declared weak-fair transition, whether the closed
walk takes it or visits a state where it is disabled. Returning to the entry is accepted only when
every weak-fair transition is seen or disabled and the property-specific violation remains true.
Search ordering chooses the shortest fair violating lasso, then canonical transition sequence and
state fingerprint.

For each candidate lasso:

1. select the shortest reachable prefix;
2. select the shortest reproducible cycle under canonical transition ordering;
3. verify pending obligations and absence of accepted recurring progress;
4. reject only those lassos that violate an explicit weak-fairness declaration;
5. exclude complete valid gate/wait contracts and accepted recurring-service outcomes;
6. retain source references, state deltas, enabled/disabled reasons, and deterministic repair
   candidates.

A valid external gate or intentional wait must have an accountable owner, observable source,
time/correction behavior, modeled return or terminal boundary, and lawful escalation or closure.
“Wait for Chairman” or “capacity may return” without those mechanics is incomplete, not live.

## 8. Task-by-task implementation crosswalk

### Task 1 — model parser

Use the corrected top-level wire in Section 3. The minimal valid test fixture includes
`abstraction_contract`, persistent-ownership arrays on outcomes, exact gate/environment shapes, and
structured model gaps. Add immutable dataclasses for the abstraction contract, environment
assumptions, and model gaps. Reject strong fairness and all unknown enum values.

### Task 2 — immutable report

Use `model_analysis_verdict` and `source_applicability_at_generation`. Do not implement
`assurance_verdict`, `current_projection_verdict`, bare `source_applicability`, or
`mastermind.operation_assurance_status.v1`. Include realizability and invalidating-gap fields on
counterexamples. Compute report identity from the non-circular canonical body defined in Section 4;
do not include wall-clock duration in the canonical exploration receipt.

### Task 3 — deterministic BFS and safety

All tests and code inspect `model_analysis_verdict`, not `assurance_verdict`. A transition-forbidden
witness is checked before accepting the forbidden successor. Bounds can weaken the no-witness result
but cannot hide a concrete already-found model witness.

### Task 4 — workflow soundness

Option-to-complete, proper completion, and required-transition reachability remain separate property
results. Proper completion honors persistent residue only when the reached outcome explicitly lists
the exact persistent obligation/resource IDs it owns.

### Task 5 — liveness and fairness

Analyze all reachable cyclic SCCs and search the augmented fairness product for the shortest fair
violating closed walk. A lasso may combine simple cycles. Weak fairness can exclude only a closed walk
where its named transition is enabled in every visited cycle state and never occurs. Strong fairness
remains outside the wave.

### Task 6 — final composition

Apply Sections 5–7. Do not use the parent plan’s blanket gap-over-counterexample ordering. Preserve
model analysis while separately composing generation-time applicability and recommendation.

### Task 7 — CLI and fixtures

The CLI remains report-only. Unsafe valid models exit normally with JSON. Invalid JSON or a refused
closed model uses the bounded invalid-input exit. Fixtures implement the corrected expectations in
Section 9.

### Task 8 — adversarial fence

Keep every original mutation falsifier and add every fidelity, applicability, immutable-report,
cycle, gate, and recommendation mutation in Section 10. Verify deterministic serialization and zero
core side effects.

## 9. Corrected fixture expectations

| Fixture | Controlling expectation |
|---|---|
| `safe_finite.json` | PROVEN_WITHIN_FINITE_MODEL + AUTHOR_DECLARED_ONLY + REPORT_ONLY_NO_RECOMMENDATION |
| `effect_unknown_failover.json` | UNSAFE_COUNTEREXAMPLE + DECLARED_MODEL_ONLY + REPORT_ONLY_REPAIR |
| `stale_projection.json` | preserves the model-analysis result while setting generation-time applicability to STALE or CONFLICTED and recommendation REPORT_ONLY_RECONCILE |
| `chairman_external_gate.json` | complete explicit release/refusal or terminal-assessment behavior; EXTERNALLY_GATED + REPORT_ONLY_AWAIT_GATE without autonomous claim |
| `capacity_valid_wait.json` | complete owned review/re-entry/cancel behavior; INTENTIONAL_WAIT + REPORT_ONLY_AWAIT_GATE without deadlock |
| `watcher_self_deadlock.json` | unsafe ownerless/non-progress lasso with prefix and cycle |
| `dialogue_carrier_split.json` | unsafe exact-carrier/return-path property |
| `stranded_parent.json` | unsafe parent-continuation property |
| `recurring_service.json` | recurring progress owned explicitly; no forced terminal completion |
| `weak_fair_starvation.json` | fairness-valid starvation witness naming the pending obligation |

The safe fixture’s proof is only proof of its declared finite model. It is not current operational
attestation.

## 10. Required mutation falsifiers

OLS-A1 tests must fail under at least these forbidden mutations:

1. remove required `abstraction_contract` parsing;
2. accept an unknown fidelity, preservation, validation, applicability, realizability, or fairness
   enum;
3. let `DECLARED_EXACT` plus `AUTHOR_DECLARATION` emit `REPORT_ONLY_PROCEED`;
4. turn an under-approximate no-witness result into proof;
5. treat an over-approximate counterexample as source-realizable;
6. let an unrelated non-load-bearing gap hide a definite witness;
7. let a relevant load-bearing gap leave witness certainty unchanged;
8. collapse `model_analysis_verdict` into source applicability;
9. accept `MODEL_STALE_OR_INVALID` as a model-analysis verdict;
10. persist `current_projection_verdict` or bare `source_applicability` in the immutable report;
11. mutate or re-hash an existing report because a current source later changes;
12. emit `mastermind.operation_assurance_status.v1` from OLS-A1;
13. treat telemetry alone as `RUNTIME_REPLAY_CONFIRMED`;
14. search only simple or closed SCC cycles and miss a fair violating closed walk that combines
    multiple cycles or ignores an outgoing completion edge;
15. infer weak fairness without a declaration;
16. accept strong fairness;
17. accept a gate with a missing required field instead of refusing the model;
18. accept a syntactically complete gate with no realizable release or terminal assessment boundary;
19. ignore terminal non-persistent residue;
20. ignore a pending parent-continuation obligation;
21. accept retry or failover from `EFFECT_UNKNOWN`;
22. select the first discovered instead of the shortest canonical counterexample;
23. omit the cycle from a liveness witness;
24. compute report identity circularly or include nondeterministic wall-clock duration;
25. allow one-sided or mismatched fairness/environment-assumption references;
26. order duplicate effects instead of rejecting them;
27. return non-zero for a valid unsafe report and thereby create an implicit gate;
28. perform network, socket, subprocess, telemetry, filesystem-write, SQLite, runtime, or
    source-owner I/O in the core.

## 11. Completion and later-wave boundary

Protecting this overlay makes only the OLS-F0 task precedence coherent. It does not build the model
parser, checker, report, CLI, source compiler, current-status compositor, Control Room experience,
admission attachment, runtime conformance, canary, or enforcement.

OLS-A1 stops at the pure report-only CLI and hostile fixture corpus. OLS-A2 remains gated on an
accepted OLS-A1 result and a corrected protected Executive Steward or canonically superseding
normalized-read owner. OLS-A3 and later product/runtime waves remain separate. No downstream wave may
claim current operational proof from an OLS-A1 authored fixture.
