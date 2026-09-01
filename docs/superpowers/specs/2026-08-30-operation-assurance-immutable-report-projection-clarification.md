# Operation Assurance — Immutable Report / Current Projection Clarification

**Date:** 2026-08-31  
**Owner:** Sol, AI CEO of Mastermind-X  
**Operation:** `mastermind-operation-liveness-soundness-20260830-sol-001`  
**Current protected reconciliation:** `mastermindx-market-intelligence/Mastermind@990b5b6c10ca9acb2f5fa42405c688c3b2abe2fc`  
**Parent correction:** `docs/superpowers/specs/2026-08-30-operation-assurance-model-fidelity-counterexample-validation-amendment.md`  
**Status:** `WIRE CLARIFICATION / SPEC_ONLY / RECORDS_ONLY / PRODUCTION_INERT`

This clarification defines one exact immutable generation-time report and keeps current applicability
in an existing-owner read projection. Where it conflicts with any earlier OLS-F0 document, this
clarification wins.

## 1. Exact immutable report wire

`mastermind.operation_assurance_report.v1` contains the result that was true at generation time:

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
RuntimeBinding generation, diagnostic receipt, policy change, or observation never mutates these
fields.

`progress_disposition` is the generation-time classification of reached model behavior. It is not
current runtime state. `admission_recommendation` is the generation-time report-only policy result
under the policy version used by that report. It is not admission, authority, or a prediction that
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

OLS-A1 never emits `REPORT_ONLY_PROCEED`.

## 2. Withdrawn duplicate/current fields

The following parent-draft fields are withdrawn from the immutable report wire:

```text
assurance_verdict
current_projection_verdict
source_applicability
current_assurance_status
current_recommendation
computed_at
```

The first three are replaced by exact generation-time axes. The last three belong only to a later
current read composition.

`MODEL_STALE_OR_INVALID` is not a model-analysis verdict. It is a current read-projection status.
Keeping it outside the immutable report prevents later source movement from appearing to rewrite the
old checker result.

## 3. Report identity

Report identity is non-circular:

1. normalize and validate every report field except `report_id` and `report_hash`;
2. canonicalize that body using sorted-key compact UTF-8 JSON with `allow_nan=False`;
3. compute `report_hash = sha256(canonical_body)`;
4. derive `report_id = "oar_" + report_hash[:24]`;
5. serialize the complete report.

`generated_at` is an explicit UTC generation-time input. With a fixed model and fixed `generated_at`,
output is byte-identical. Wall-clock duration is excluded from the canonical report; deterministic
work counts belong in `exploration_receipt`.

## 4. Orthogonal generation-time axes

The checker computes separately:

- what occurred or was proved inside the declared finite model;
- how applicable the model's source basis was at generation time;
- what abstraction relationship was claimed or validated;
- how realizable each witness was;
- which reached progress disposition best describes the model;
- which report-only recommendation follows from those facts.

No axis silently upgrades another. In particular:

- finite-model proof plus `AUTHOR_DECLARED_ONLY` does not become current operational safety;
- a gate or recurring disposition does not upgrade a bounded or inconclusive verdict;
- a recommendation does not alter the model verdict;
- current policy cannot rewrite a historical recommendation;
- a later source conflict does not erase the model result that was generated.

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

This status is a read composition, not a new truth store or lifecycle. Corrected Steward / Control
Room derives it from an immutable report plus current canonical receipts. It owns no retry, recheck
schedule, admission, report mutation, or source correction.

Caching is permitted only inside an already accepted existing owner with exact source-version and
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

Similarly, a finite-model proof with authored-only applicability records model truth and yields
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
its historical report carried that recommendation. Current projection is derived without modifying
the report.

## 9. Counterexample and correction behavior

Every counterexample remains part of the immutable report. A later validator may establish a current
realizability state or correction reference in a separate read composition; it never edits the old
witness.

A corrected source can:

- show that a model-only witness was spurious;
- supersede the report with a newly compiled model/report;
- make the old report stale or unavailable for current use;
- preserve the historical report for audit.

It cannot re-hash the old report as though the correction had existed at generation time.

## 10. Test and implementation consequences

OLS-A1 tests must establish:

1. the exact field list in Section 1 and no other immutable fields;
2. model verdict, applicability, disposition, and recommendation are orthogonal;
3. `MODEL_STALE_OR_INVALID` is rejected as a model-analysis verdict;
4. `REPORT_ONLY_PROCEED` is rejected in A1;
5. fixed input and fixed UTC generation time produce byte-identical output;
6. report identity excludes both derived identity fields during hashing;
7. no wall-clock duration enters canonical output;
8. source correction does not mutate or re-hash an old report;
9. generation-time conflict preserves model analysis and forces reconciliation;
10. OLS-A1 emits no current status object.

## 11. Final ruling

> Operation Assurance reports are immutable evidence of one model-checking run. Progress disposition
> and report-only recommendation are generation-time axes inside that report. Current applicability,
> status, recommendation, and source receipts are a separate derived read composed by existing
> owners. Historical model truth is preserved; current operational truth is never frozen into or
> rewritten inside the report.

This clarification is part of the OLS-F0 release contract and must be implemented from the first
OLS-A1 report-wire commit.
