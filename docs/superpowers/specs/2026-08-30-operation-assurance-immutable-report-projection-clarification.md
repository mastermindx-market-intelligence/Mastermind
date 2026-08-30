# Operation Assurance — Immutable Report / Current Projection Clarification

**Date:** 2026-08-30  
**Owner:** Sol, AI CEO of Mastermind-X  
**Operation:** `mastermind-operation-liveness-soundness-20260830-sol-001`  
**Current protected reconciliation:** `mastermindx-market-intelligence/Mastermind@be4cb72c7c6c663ae7c09a7e2d22543ab406b027`  
**Parent correction:** `docs/superpowers/specs/2026-08-30-operation-assurance-model-fidelity-counterexample-validation-amendment.md`  
**Status:** `WIRE CLARIFICATION / SPEC_ONLY / RECORDS_ONLY / PRODUCTION_INERT`

This clarification removes one duplicate field introduced during the model-fidelity correction. An
immutable assurance report cannot also contain a field whose meaning changes whenever canonical
sources advance. Current applicability must be derived by existing read/product owners, not written
back into the historical report.

Where this clarification conflicts with any earlier OLS-F0 document, it wins.

## 1. Immutable report wire

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

The report is content-addressed and immutable. A later correction, new Git commit, new Executive
Event, new RuntimeBinding generation, later diagnostic receipt, or later observation never mutates
these fields.

## 2. Withdrawn duplicate fields

The following parent-draft fields are **withdrawn from the immutable report wire before
implementation**:

```text
assurance_verdict
current_projection_verdict
source_applicability
```

They are replaced by the exact generation-time fields:

```text
model_analysis_verdict
source_applicability_at_generation
```

`MODEL_STALE_OR_INVALID` is not a model-analysis verdict. It is a current read-projection status.
Keeping it out of the immutable report prevents a later source movement from appearing to rewrite the
old model checker result.

## 3. Current derived read projection

After OLS-A2/A3, corrected Executive Steward / Control Room may derive a non-persisted or
existing-owner-cached value:

```text
mastermind.operation_assurance_status.v1
```

Conceptual fields:

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

This status is a read composition, not a new truth store or lifecycle. Corrected Steward/Control Room
must derive it from the immutable report plus current canonical source receipts. It owns no retry,
recheck schedule, admission, report mutation, or source correction.

## 4. OLS-A1 boundary

OLS-A1 emits only `mastermind.operation_assurance_report.v1`.

Because OLS-A1 accepts authored files and has no canonical source compiler:

```text
source_applicability_at_generation = AUTHOR_DECLARED_ONLY
```

unless a fixture intentionally represents stale/conflicting/incomplete source evidence for a
negative test. OLS-A1 does not emit `mastermind.operation_assurance_status.v1`, does not read current
owners after checking, and does not claim the report is current for a live operation.

## 5. Generation-time stale/conflict behavior

A model may include stale/conflicting source receipts so the checker can explain the model result and
why it is not operationally applicable.

Example:

```text
model_analysis_verdict = UNSAFE_COUNTEREXAMPLE
source_applicability_at_generation = CONFLICTED
counterexample.realizability = DECLARED_MODEL_ONLY
admission_recommendation = REPORT_ONLY_RECONCILE
```

This does not claim the current operation is unsafe. It truthfully preserves that the declared model
contained a counterexample while the source basis was conflicted.

A source-validated or runtime-replayed counterexample may be operationally actionable only when its
validation receipts are current or explicitly historical for the stated replay scope.

## 6. Recommendation placement

The immutable report may contain a generation-time report-only recommendation, but it cannot predict
future source applicability.

Current Control Room recommendation is recomputed from:

```text
immutable report recommendation
+ current source applicability
+ supersession state
+ current report-only policy
```

A stale/superseded report can never retain a current `REPORT_ONLY_PROCEED` projection merely because
its historical report carried that recommendation.

## 7. Test correction

OLS-A1 tests must assert:

1. immutable reports contain `model_analysis_verdict` and
   `source_applicability_at_generation`;
2. immutable reports contain neither `current_projection_verdict` nor the ambiguous bare
   `source_applicability` field;
3. `MODEL_STALE_OR_INVALID` is rejected as `model_analysis_verdict`;
4. changing a current source receipt does not mutate or re-hash an existing report;
5. OLS-A1 emits no current status object;
6. generation-time conflicted input can preserve model analysis while forcing
   `REPORT_ONLY_RECONCILE`;
7. a later OLS-A3 projection test derives stale/superseded status without modifying the report.

## 8. Final ruling

> Operation Assurance reports are immutable evidence of one model-checking run. Current applicability
> is a separate derived read composed by existing owners. Historical model truth is preserved;
> current operational truth is never frozen into or rewritten inside the report.

This clarification is part of the OLS-F0 release contract and must be implemented from the first
OLS-A1 report-wire commit.
