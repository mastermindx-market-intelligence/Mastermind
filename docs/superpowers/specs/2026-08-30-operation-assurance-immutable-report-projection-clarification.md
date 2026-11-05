# Operation Assurance — Immutable Report / Current Projection Clarification

**Date:** 2026-08-31  
**Owner:** Sol, AI CEO of Mastermind-X  
**Operation:** `mastermind-operation-liveness-soundness-20260830-sol-001`  
**Current protected reconciliation:** `mastermindx-market-intelligence/Mastermind@e60f69aa10e67b1334b1fa6a3299cb90fbbde7ab`  
**Parent correction:** `docs/superpowers/specs/2026-08-30-operation-assurance-model-fidelity-counterexample-validation-amendment.md`  
**Status:** `WIRE CLARIFICATION / SPEC_ONLY / RECORDS_ONLY / PRODUCTION_INERT`

This clarification defines one exact immutable generation-time report and keeps current applicability
inside an existing-owner read projection. Where it conflicts with any earlier OLS-F0 document, this
clarification wins. It creates no report database, source compiler, recheck scheduler, admission
gate, retry path, runtime write, or product authority.

## 1. Exact immutable report wire

`mastermind.operation_assurance_report.v1` contains exactly:

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

The report is content-addressed and immutable. A later correction, Git commit, Executive event,
RuntimeBinding generation, diagnostic receipt, policy change, or observation never mutates these fields.

`progress_disposition` is a generation-time classification of reached model behavior. It is not
current runtime state. `admission_recommendation` is the generation-time report-only result under the
checker/property-set version bound into the report. It is not admission, authority, or a promise that
the recommendation remains current.

Closed `model_analysis_verdict` values:

```text
UNSAFE_COUNTEREXAMPLE
PROVEN_WITHIN_FINITE_MODEL
BOUNDED_NO_COUNTEREXAMPLE
INCONCLUSIVE_MODEL_GAP
```

Closed `source_applicability_at_generation` values:

```text
AUTHOR_DECLARED_ONLY
CURRENT_SOURCE_ATTESTED
HISTORICAL_SOURCE_ATTESTED
STALE
CONFLICTED
INCOMPLETE
UNKNOWN
```

Closed `progress_disposition` values:

```text
AUTONOMOUSLY_LIVE
FAIRNESS_CONDITIONAL
EXTERNALLY_GATED
INTENTIONAL_WAIT
RECURRING_SERVICE
NO_PROGRESS
UNKNOWN
```

Closed OLS-A1 `admission_recommendation` values:

```text
REPORT_ONLY_REPAIR
REPORT_ONLY_RECONCILE
REPORT_ONLY_AWAIT_GATE
REPORT_ONLY_NO_RECOMMENDATION
```

OLS-A1 rejects `REPORT_ONLY_PROCEED`.

### 1.1 Property result

Every mandatory generic property and every authored safety property has exactly one result:

```text
property_id
property_kind
status
analysis_complete
counterexample_id|null
reason_codes[]
source_refs[]
```

Closed `status` values are:

```text
PASS | FAIL | UNKNOWN | NOT_APPLICABLE
```

`analysis_complete` states whether the load-bearing analysis for this property completed. It is not
inferred from the status. `FAIL` references exactly one complete counterexample. `UNKNOWN` may
reference one complete candidate witness when the witness is potentially spurious or the result is
limited by a relevant gap. `PASS` and `NOT_APPLICABLE` have `counterexample_id = null`.

`NOT_APPLICABLE is legal only` for these generic properties and exact absence conditions:

- `RECURRING_PROGRESS_VALID when the model declares no recurring outcome`;
- `NO_STARVATION_UNDER_DECLARED_FAIRNESS when the model declares no persistent obligation`;
- `FAIRNESS_REALIZABLE when the model declares no fairness assumption`.

Every other mandatory property and every authored safety property must be PASS, FAIL, or UNKNOWN.
A `NOT_APPLICABLE` result is complete and must carry the reason code for its exact absence condition.

Closed `property_kind` values are:

```text
AUTHORED_STATE_SAFETY
AUTHORED_TRANSITION_SAFETY
OPTION_TO_COMPLETE
PROPER_COMPLETION
NO_DEAD_REQUIRED_TRANSITION
NO_POST_TERMINAL_TRANSITION
GATE_OR_WAIT_RETURN_PATH_VALID
UNIVERSAL_PROGRESS
RECURRING_PROGRESS_VALID
NO_STARVATION_UNDER_DECLARED_FAIRNESS
FAIRNESS_REALIZABLE
```

### 1.2 Counterexample

Every failed property and every retained potentially spurious candidate has one deterministic object:

```text
counterexample_id
witness_kind
property_id
realizability
validation_refs[]
invalidating_gap_ids[]
initial_state
shortest_prefix[]
cycle[]
state_delta_per_step[]
enabled_and_disabled_transition_reasons[]
source_refs[]
repair_candidates[]
limitations[]
```

Closed `witness_kind` values:

```text
TRACE
LASSO
GLOBAL_CERTIFICATE
```

Closed `realizability` values:

```text
DECLARED_MODEL_ONLY
SOURCE_CONTRACT_VALIDATED
RUNTIME_REPLAY_CONFIRMED
POTENTIALLY_SPURIOUS
INVALIDATED
```

OLS-A1 may emit only `DECLARED_MODEL_ONLY` or `POTENTIALLY_SPURIOUS`; authored validation labels
cannot mint a stronger state.

`initial_state` is the canonical variable-to-value map. `shortest_prefix` and `cycle` are ordered
transition-ID sequences. Safety traces use an empty cycle. Liveness and starvation witnesses use a
non-empty cycle. `GLOBAL_CERTIFICATE` is reserved for global absence defects such as a dead required
transition or unrealizable fairness; it may use empty trace sequences and must provide the canonical
coverage/reason evidence that proves the absence.

Counterexample identity is non-circular. Canonicalize:

```text
model_hash
+ counterexample body excluding counterexample_id
```

and compute:

```text
counterexample_id = "ocx_" + counterexample_hash[:24]
```

### 1.3 State delta step

Every realized transition in a trace or lasso has one ordered delta record:

```text
segment = PREFIX | CYCLE
step_index
from_state_fingerprint
transition_id
to_state_fingerprint
changes[]
```

Each `changes` item is:

```text
variable
before
after
```

Changes are sorted by variable. `step_index` is zero-based inside its segment. A self-loop has an empty
`changes` array but still names the transition and identical state fingerprints.

### 1.4 Transition-reason snapshot

The report explains enabled and disabled alternatives using ordered snapshots:

```text
segment = PREFIX | CYCLE | FINAL
step_index
state_fingerprint
enabled_transition_ids[]
disabled_transitions[]
```

Each disabled transition is:

```text
transition_id
reason_codes[]
guard_failures[]
```

Each guard failure is:

```text
variable
op
expected
actual
```

Reason codes and guard failures are deterministic and secret-free. The generic checker reports only
closed grammar/analysis reasons; it never invents runtime authority or source facts from token names.

### 1.5 Repair candidate

Every repair candidate is non-executable:

```text
repair_id
kind
target_ids[]
summary
source_refs[]
```

Closed generic `kind` values:

```text
ADD_OR_CORRECT_TRANSITION
DISCHARGE_OBLIGATION
RELEASE_RESOURCE
ADD_OR_CORRECT_TERMINAL_OUTCOME
ADD_OR_CORRECT_RECURRING_OUTCOME
ADD_OR_CORRECT_GATE_RETURN
RECONCILE_SOURCE
RECONCILE_EFFECT
RECONCILE_AUTHORITY_OR_BINDING
REVISE_FAIRNESS_ASSUMPTION
REDUCE_MODEL_GAP
INCREASE_DECLARED_BOUND
```

A repair candidate names the model/source contract that requires human or owner action. It is never a
prepared action, command, credential, retry authorization, or lifecycle mutation.

### 1.6 Coverage

`coverage` contains exactly:

```text
mandatory_property_ids[]
authored_property_ids[]
evaluated_property_ids[]
complete_property_ids[]
incomplete_property_ids[]
not_applicable_property_ids[]
```

All arrays are sorted unique IDs. `evaluated_property_ids` equals the union of mandatory generic and
authored safety property IDs. Each evaluated ID appears in exactly one of complete or incomplete.
Every `property_results` ID is represented in coverage and vice versa.

### 1.7 Assumptions

`assumptions` contains exactly:

```text
declared_fairness_assumption_ids[]
fairness_assumption_ids_used_to_exclude_candidates[]
declared_environment_assumption_ids[]
environment_assumption_ids_required_by_results[]
```

These arrays preserve which assumptions affected the finite-model result. An authored assumption is a
model premise, not source attestation, scheduler authority, or a promise that a human/external event
will occur.

### 1.8 Exploration receipt and analysis product

`exploration_receipt` contains exactly:

```text
checker_terminated_normally
base_graph_complete
declared_limits
states_discovered
edges_materialized
transitions_considered
maximum_depth_reached
peak_frontier
state_limit_reached
depth_limit_reached
analysis_products[]
```

`declared_limits` contains the normalized `max_states` and `max_depth`.

Each `analysis_products` item contains exactly:

```text
analysis_id
complete
states_examined
transitions_considered
limit_reason|null
```

`analysis_id` is a stable generic analysis/property ID or an authored property ID. Closed non-null
`limit_reason` values are:

```text
STATE_LIMIT_REACHED
DEPTH_LIMIT_REACHED
FAIRNESS_PRODUCT_STATE_LIMIT_REACHED
DEPENDENT_ANALYSIS_INCOMPLETE
```

The base graph and every load-bearing derived product expose completion separately.
`checker_terminated_normally = true` is necessary but insufficient for proof.

## 2. Withdrawn duplicate/current fields

The following parent-draft fields are withdrawn from the immutable report wire:

```text
assurance_verdict
current_projection_verdict
source_applicability
current_assurance_status
current_recommendation
computed_at
duration_ms
```

The first three are replaced by exact generation-time axes. Current status/recommendation/receipts and
recomputation time belong only to a later read composition. Wall-clock duration is diagnostic and
cannot enter canonical identity.

`MODEL_STALE_OR_INVALID` is not a model-analysis verdict. It is a current read-projection status.
Keeping it outside the immutable report prevents later source movement from appearing to rewrite an
old checker result.

## 3. Report identity and canonical ordering

Report identity is non-circular:

1. normalize and validate every report field except `report_id` and `report_hash`;
2. canonicalize that body using sorted-key compact UTF-8 JSON with `allow_nan=False`;
3. compute `report_hash = sha256(canonical_body)`;
4. derive `report_id = "oar_" + report_hash[:24]`;
5. serialize the complete report.

`generated_at` is an explicit UTC generation-time input in canonical second-precision `...Z` form.
With a fixed model and fixed `generated_at`, output is byte-identical.

Top-level set-like arrays, property results, counterexamples, analysis products, reason codes, source
refs, repair candidates, and limitations use the deterministic normalization law frozen in the A1
plan. Trace order is never re-sorted.

## 4. Cross-field anti-inflation invariants

The immutable report validator refuses any document that violates these rules:

- every mandatory generic property and authored safety property appears exactly once;
- duplicate property, counterexample, repair, or analysis IDs are refused;
- `FAIL` has one referenced complete counterexample whose `property_id` matches;
- `UNKNOWN` may reference one candidate; `PASS` and `NOT_APPLICABLE` reference none;
- every counterexample is referenced by exactly one property result;
- `UNSAFE_COUNTEREXAMPLE` requires at least one definite failed property;
- `PROVEN_WITHIN_FINITE_MODEL` requires complete base graph, complete load-bearing analysis products,
  every property `PASS` or legally `NOT_APPLICABLE`, normal termination, finite domains, and a
  property-preserving abstraction;
- `BOUNDED_NO_COUNTEREXAMPLE` requires at least one declared resource-bound receipt, no complete
  definite counterexample, and no claim of complete proof;
- a relevant load-bearing model gap or potentially spurious witness prevents proof;
- a source applicability value never changes the model-analysis verdict;
- a progress disposition never upgrades a bounded or inconclusive verdict;
- A1 never emits `REPORT_ONLY_PROCEED`;
- an internal checker exception never becomes `checker_terminated_normally = true` or a healthy
  default.

## 5. Current derived read projection

After OLS-A2/A3, corrected Executive Steward / Control Room may derive:

```text
mastermind.operation_assurance_status.v1
```

Conceptual current fields:

```text
report_id
current_source_applicability
current_assurance_status
current_recommendation
current_source_receipts
supersession_or_correction_refs
computed_at
```

Closed `current_assurance_status` values:

```text
CURRENT
MODEL_STALE_OR_INVALID
SOURCE_STATUS_INCONCLUSIVE
REPORT_SUPERSEDED
REPORT_UNAVAILABLE
```

This status is a read composition, not a new truth store or lifecycle. Corrected Executive Steward /
Control Room derives it from the immutable report plus current canonical receipts. It owns no retry, recheck schedule, admission, report mutation, or source correction.

Caching is legal only inside an already accepted existing owner with exact source-version and
supersession behavior. This clarification creates no assurance database, scheduler, or poller.

## 6. OLS-A1 authored-input boundary

OLS-A1 emits only `mastermind.operation_assurance_report.v1`.

For ordinary authored input:

```text
source_applicability_at_generation = AUTHOR_DECLARED_ONLY
```

A negative fixture may produce `STALE`, `CONFLICTED`, `INCOMPLETE`, or `UNKNOWN`. Authored compiler
names, timestamps, source refs, validation refs, or validation-kind labels cannot produce
`CURRENT_SOURCE_ATTESTED` or `HISTORICAL_SOURCE_ATTESTED`.

OLS-A1 does not emit `mastermind.operation_assurance_status.v1`, does not fetch owners after checking,
and does not claim the report is current for a live operation.

## 7. Generation-time conflict behavior

A conflicted source basis can preserve model analysis while refusing an operational claim:

```text
model_analysis_verdict = UNSAFE_COUNTEREXAMPLE
source_applicability_at_generation = CONFLICTED
counterexample.realizability = DECLARED_MODEL_ONLY
progress_disposition = NO_PROGRESS
admission_recommendation = REPORT_ONLY_RECONCILE
```

This does not claim the current operation is unsafe. It records that the declared model contained a
counterexample while the source basis was conflicted.

A finite-model proof with authored-only applicability likewise records model truth and yields
`REPORT_ONLY_NO_RECOMMENDATION`, not permission to proceed.

## 8. Current recommendation composition

A later current recommendation is recomputed by the existing read/product owner from:

```text
immutable generation-time recommendation
+ current source applicability
+ report supersession state
+ current report-only policy
+ current authority/serviceability facts
```

A stale/superseded report can never retain a current `REPORT_ONLY_PROCEED` projection merely because
its historical report carried that recommendation. Current projection is derived without modifying the report.

## 9. Counterexample correction and supersession

Every counterexample remains part of the immutable report. A later validator may establish current
realizability or a correction reference in a separate read composition; it never edits the old
witness.

A corrected source can show that a model-only witness was spurious, supersede the report with a newly
compiled model/report, make the old report stale or unavailable for current use, and preserve the
historical report for audit. It cannot re-hash the old report as though the correction existed at
generation time.

## 10. Required source-law and implementation tests

OLS-A1 tests must establish:

1. the exact top-level and nested field sets in Section 1;
2. model verdict, applicability, fidelity, realizability, disposition, and recommendation remain
   orthogonal;
3. `MODEL_STALE_OR_INVALID` is rejected as a model-analysis verdict;
4. `REPORT_ONLY_PROCEED` is rejected in A1;
5. fixed input and fixed UTC generation time produce byte-identical output;
6. report and counterexample identity exclude their derived IDs during hashing;
7. no wall-clock duration enters canonical output;
8. current source correction does not mutate or re-hash an old report;
9. generation-time conflict preserves model analysis and forces reconciliation;
10. OLS-A1 emits no current status object;
11. `NOT_APPLICABLE` is accepted only for the exact absence cases in Section 1.1;
12. coverage and analysis-product completion are sufficient to prove that every load-bearing
    analysis ran.

## 11. Final ruling

> Operation Assurance reports are immutable evidence of one model-checking run. Progress disposition
> and report-only recommendation are generation-time axes inside that report. Current applicability,
> status, recommendation, and source receipts are a separate derived read composed by existing
> owners. Historical model truth is preserved; current operational truth is never frozen into or
> rewritten inside the report.

This clarification is part of the OLS-F0 release contract and must be implemented from the first
OLS-A1 report-wire commit.
