# Operation Assurance — Model Fidelity & Counterexample Validation Amendment

**Date:** 2026-08-30  
**Owner:** Sol, AI CEO of Mastermind-X  
**Operation:** `mastermind-operation-liveness-soundness-20260830-sol-001`  
**Current protected reconciliation:** `mastermindx-market-intelligence/Mastermind@be4cb72c7c6c663ae7c09a7e2d22543ab406b027`  
**Parent law:** `docs/OPERATION_LIVENESS_SOUNDNESS_LAW.md`  
**Parent design:** `docs/superpowers/specs/2026-08-30-operation-liveness-soundness-design.md`  
**Parent implementation plan:** `docs/superpowers/plans/2026-08-30-operation-assurance-core.md`  
**Status:** `NARROW PRECEDENCE AMENDMENT / SPEC_ONLY / RECORDS_ONLY / PRODUCTION_INERT`

This amendment closes a blocker found during adversarial Program CEO review of OLS-F0. The original
architecture correctly separates complete finite proof from bounded exploration, but it does not
make the **fidelity of the analysis model to its source contracts** sufficiently explicit. Without
that axis, an over-approximating abstraction could produce a spurious counterexample that appears
operationally certain, an under-approximating model could appear complete, or a hand-authored fixture
could yield a misleading operational `PROCEED` recommendation.

Where this amendment conflicts with the parent law, design, plan, or PR prose, this amendment wins.
It does not change the accepted hybrid architecture, owner boundaries, report-only policy, or OLS-A1
path boundary.

## 1. Corrected truth model

Operation Assurance reports four independent questions:

1. **Model verdict:** what is true in the exact declared finite transition model?
2. **Source applicability:** is that model current and valid for the claimed canonical operation?
3. **Abstraction fidelity:** what relationship has been established between the finite model and the
   source/concrete system?
4. **Counterexample realizability:** is a model witness known to correspond to a source-valid or
   runtime-replayed operation path?

None may silently upgrade another.

A finite-model proof remains exactly that: a proof about the complete declared finite model. It is
not automatically a proof that the model is a faithful abstraction of the deployed organization.

## 2. Required abstraction contract

`mastermind.operation_assurance_model.v1` adds a required top-level object:

```json
{
  "abstraction_contract": {
    "kind": "DECLARED_EXACT",
    "concrete_scope": "one closed pre-admission fixture operation",
    "preserves": ["SAFETY", "LIVENESS_UNDER_DECLARED_FAIRNESS"],
    "introduced_behavior": "NONE_DECLARED",
    "excluded_behavior": "NONE_DECLARED",
    "validation_kind": "AUTHOR_DECLARATION",
    "validation_refs": ["Mastermind@<sha>"],
    "notes": []
  }
}
```

Closed `kind` vocabulary:

```text
DECLARED_EXACT
SOUND_OVERAPPROXIMATION
TRACE_BACKED_UNDERAPPROXIMATION
HEURISTIC_ABSTRACTION
UNKNOWN_FIDELITY
```

Closed `preserves` vocabulary:

```text
SAFETY
REACHABLE_COUNTEREXAMPLE
OPTION_TO_COMPLETE
UNIVERSAL_PROGRESS
LIVENESS_UNDER_DECLARED_FAIRNESS
RESOURCE_OWNERSHIP
EFFECT_RETRY_SAFETY
```

Closed `introduced_behavior` and `excluded_behavior` vocabularies:

```text
NONE_DECLARED
MAY_EXIST
KNOWN_PRESENT
UNKNOWN
```

Closed `validation_kind` vocabulary:

```text
AUTHOR_DECLARATION
SOURCE_COMPILER_ATTESTATION
SOURCE_CONTRACT_REPLAY
RUNTIME_EVENT_REPLAY
INDEPENDENT_FORMAL_EQUIVALENCE
NONE
```

`concrete_scope` and `notes` are bounded explanatory text only. They grant no proof or preservation
semantics. The closed enum fields control checker/report behavior.

### 2.1 Semantics

#### `DECLARED_EXACT`

The model author declares that all relevant states/transitions inside `concrete_scope` are represented
without deliberate introduction or exclusion. In OLS-A1 this supports proof only **within the declared
model**. `AUTHOR_DECLARATION` does not establish current operational applicability and cannot produce
`REPORT_ONLY_PROCEED`.

#### `SOUND_OVERAPPROXIMATION`

The model may include behaviors not present in the concrete system but claims not to exclude concrete
behaviors relevant to the declared `preserves` properties. An absence-of-violation result may support
the properties explicitly preserved by the abstraction. A counterexample may be spurious until its
path is validated against source contracts or replayed.

#### `TRACE_BACKED_UNDERAPPROXIMATION`

The model contains only source-valid or observed behavior slices but may omit other concrete
behavior. A validated witness can be actionable. Absence of a counterexample cannot support proof of
universal safety, option-to-complete, or liveness.

#### `HEURISTIC_ABSTRACTION`

The relationship to the source system is intentionally approximate. Results are diagnostic only.
Neither proof nor an operationally certain counterexample is allowed without separate validation.

#### `UNKNOWN_FIDELITY`

No usable abstraction relationship has been established. The strongest assurance verdict is
`INCONCLUSIVE_MODEL_GAP`, although the report may carry model-only candidate witnesses.

## 3. Source applicability axis

`mastermind.operation_assurance_report.v1` adds:

```text
source_applicability
```

Closed values:

```text
AUTHOR_DECLARED_ONLY
CURRENT_SOURCE_ATTESTED
HISTORICAL_SOURCE_ATTESTED
STALE
CONFLICTED
INCOMPLETE
UNKNOWN
```

Rules:

- OLS-A1 hand-authored/fixture models use `AUTHOR_DECLARED_ONLY`.
- Only a protected canonical source compiler may emit `CURRENT_SOURCE_ATTESTED` or
  `HISTORICAL_SOURCE_ATTESTED`.
- A current owner correction after compilation changes the current projection to `STALE`; it never
  rewrites the immutable historical report.
- Conflicting canonical source receipts produce `CONFLICTED`.
- Missing load-bearing source receipts produce `INCOMPLETE`.
- Null never implies `CURRENT_SOURCE_ATTESTED`.

The parent verdict `MODEL_STALE_OR_INVALID` remains the current projection verdict for `STALE` or
`CONFLICTED` applicability. The immutable report also retains the model-analysis result in a separate
field:

```text
model_analysis_verdict
```

Closed model-analysis values:

```text
UNSAFE_COUNTEREXAMPLE
PROVEN_WITHIN_FINITE_MODEL
BOUNDED_NO_COUNTEREXAMPLE
INCONCLUSIVE_MODEL_GAP
```

This prevents a later correction from erasing what the old model actually showed while preventing
the old result from being presented as current.

## 4. Counterexample realizability axis

Every counterexample adds:

```text
realizability
validation_refs
invalidating_gap_ids
```

Closed `realizability` values:

```text
DECLARED_MODEL_ONLY
SOURCE_CONTRACT_VALIDATED
RUNTIME_REPLAY_CONFIRMED
POTENTIALLY_SPURIOUS
INVALIDATED
```

Rules:

- every checker witness begins at least as `DECLARED_MODEL_ONLY`;
- `SOURCE_CONTRACT_VALIDATED` requires the canonical compiler or a separate deterministic validator
  to confirm every prefix/cycle step against current or historical source contracts;
- `RUNTIME_REPLAY_CONFIRMED` requires accepted canonical semantic/event evidence for the whole
  witness, not only telemetry;
- an over-approximation witness remains `POTENTIALLY_SPURIOUS` until validation;
- a conflicting correction or failed validation yields `INVALIDATED` without deleting the old
  witness;
- Runtime Observability logs, metrics or traces may enrich replay evidence but cannot alone create
  `RUNTIME_REPLAY_CONFIRMED`.

The Control Room headline must render the difference, for example:

```text
UNSAFE_COUNTEREXAMPLE — SOURCE_CONTRACT_VALIDATED
```

versus:

```text
MODEL COUNTEREXAMPLE — POTENTIALLY_SPURIOUS / VALIDATION REQUIRED
```

## 5. Model-gap relevance and verdict precedence

Each `known_model_gaps` entry is amended to include:

```json
{
  "gap_id": "gap_provider_failure_semantics",
  "reason": "provider disconnect effect is opaque",
  "load_bearing": true,
  "affects_property_ids": ["NO_EFFECT_UNKNOWN_ESCAPE"],
  "affects_transition_ids": ["provider_disconnect"],
  "affects_variable_ids": ["effect.state"],
  "source_refs": ["Mastermind@<sha>"]
}
```

Empty `affects_*` arrays are permitted only when `load_bearing=false` and the reason explains why the
gap cannot alter any checked property. The parser fails closed on references to unknown identities.

### 5.1 Corrected precedence

The parent plan's blanket ordering `load-bearing model gap > concrete counterexample` is replaced by
trace/property-specific relevance:

1. malformed schema/wire -> parser refusal, no assurance report;
2. current applicability `STALE` or `CONFLICTED` -> current projection
   `MODEL_STALE_OR_INVALID`; immutable model analysis remains visible;
3. a reachable witness with `RUNTIME_REPLAY_CONFIRMED` or `SOURCE_CONTRACT_VALIDATED` and no
   invalidating relevant gap -> `UNSAFE_COUNTEREXAMPLE`;
4. a `DECLARED_MODEL_ONLY` witness in a `DECLARED_EXACT` fixture/model ->
   `UNSAFE_COUNTEREXAMPLE` **within the declared model**, source applicability
   `AUTHOR_DECLARED_ONLY`, never operationally attested;
5. an over-approximate/heuristic/unknown-fidelity witness or a witness affected by a load-bearing gap
   -> `INCONCLUSIVE_MODEL_GAP` with a `POTENTIALLY_SPURIOUS` candidate witness;
6. complete finite exploration with all properties known/pass and an abstraction contract that
   preserves those properties -> `PROVEN_WITHIN_FINITE_MODEL`;
7. incomplete exploration with no witness -> `BOUNDED_NO_COUNTEREXAMPLE`;
8. otherwise -> `INCONCLUSIVE_MODEL_GAP`.

An unrelated non-load-bearing gap does not hide a definite source-validated unsafe trace. A gap that
can invalidate the trace or checked property does.

## 6. Admission recommendation correction

OLS-A1 is a pure checker over authored fixtures/models. It cannot establish
`CURRENT_SOURCE_ATTESTED`. Therefore:

```text
OLS-A1 never emits REPORT_ONLY_PROCEED.
```

OLS-A1 recommendation rules:

- model-only unsafe witness -> `REPORT_ONLY_REPAIR` with scope `MODEL_OR_DECLARED_CONTRACT`;
- potentially spurious witness -> `REPORT_ONLY_NO_RECOMMENDATION` with validation required;
- model finite proof -> `REPORT_ONLY_NO_RECOMMENDATION` because current source applicability is not
  attested;
- bounded no counterexample -> `REPORT_ONLY_NO_RECOMMENDATION`;
- complete declared external gate/wait -> `REPORT_ONLY_AWAIT_GATE` only inside the model/fixture;
- malformed/stale/conflicted input -> refusal or `REPORT_ONLY_RECONCILE` as applicable.

`REPORT_ONLY_PROCEED` is first eligible in OLS-A2/A5 only when all are true:

```text
source_applicability = CURRENT_SOURCE_ATTESTED
abstraction contract preserves every load-bearing checked property
no relevant model gap
report is current
policy explicitly permits the exact report class
```

Even then it remains advisory until a separately accepted enforcement law says otherwise.

## 7. Liveness-cycle correction

A universal progress violation does not require a closed SCC. A reachable fairness-valid cycle may
avoid progress forever even when the SCC has an outgoing completion edge, because the execution can
keep selecting the cycle unless the declared fairness contract forbids that behavior.

Therefore OLS-A1 must analyze:

```text
all reachable cyclic SCCs
-> candidate non-progress cycles preserving an obligation
-> fairness validation
-> valid gate/wait/recurring exclusions
-> shortest deterministic lasso
```

`CLOSED_NON_PROGRESS_SCC` remains one high-confidence defect class. It is not the complete liveness
algorithm.

Example:

```text
A --spin--> A
A --finish--> DONE
```

- no fairness for `finish` -> `spin` is a valid non-progress lasso;
- weak fairness for continuously enabled `finish` -> that exact lasso is invalid;
- if `finish` is disabled in any cycle state -> weak fairness does not remove the lasso;
- strong fairness remains outside OLS-A1.

## 8. Gate/wait realizability correction

A descriptive gate object alone is not a modeled return path. A valid `EXTERNALLY_GATED` or
`INTENTIONAL_WAIT` state requires one of:

1. at least one explicit model transition referencing that `gate_id`, whose guard/effect represents
   release, escalation, cancellation, review, or lawful closure; or
2. a terminal assessment boundary that intentionally stops at the external authority and makes no
   claim about autonomous progress after the gate.

The gate must also bind its `release_condition` to the transition identity or terminal boundary.
Free-form text such as “wait for Chairman” cannot make a dead state valid.

A gate with no modeled release/terminal boundary is `EXTERNAL_GATE_INCOMPLETE` and a load-bearing
model gap.

## 9. Exact OLS-A1 wire correction

The parent plan's model schema is amended with the following exact objects.

### 9.1 Safety property

State-forbidden:

```json
{
  "property_id": "ONE_ACTION_AUTHORITY",
  "kind": "STATE_FORBIDDEN",
  "violation_when": [
    {"variable": "turn.owner_count", "op": "EQ", "value": "MULTIPLE"}
  ],
  "source_refs": ["Mastermind@<sha>"]
}
```

Transition-forbidden:

```json
{
  "property_id": "NO_EFFECT_UNKNOWN_ESCAPE",
  "kind": "TRANSITION_FORBIDDEN",
  "when": [
    {"variable": "effect.state", "op": "EQ", "value": "EFFECT_UNKNOWN"}
  ],
  "forbidden_transition_kinds": ["RETRY", "FAILOVER", "MODIFY"],
  "source_refs": ["Mastermind@<sha>"]
}
```

Unknown keys or mixed state/transition fields fail closed.

### 9.2 Fairness assumption

```json
{
  "fairness_id": "fair_finish",
  "kind": "WEAK",
  "transition_ids": ["finish"],
  "source_refs": ["Mastermind@<sha>"]
}
```

`NONE` is represented by absence of an assumption, not a fake fairness object. OLS-A1 rejects
`STRONG`.

### 9.3 Gate

```json
{
  "gate_id": "chairman_credential",
  "disposition": "EXTERNAL_GATE",
  "state_guards": [
    {"variable": "gate.chairman_credential", "op": "EQ", "value": "WAITING"}
  ],
  "owner_or_authority": "CHAIRMAN",
  "release_condition": "credential decision recorded through exact carrier",
  "release_transition_ids": ["chairman_approves", "chairman_refuses"],
  "return_or_observation_source": "operation-carrier",
  "wake_or_review_path": "existing Wake or explicit Chairman return",
  "time_contract": "no synthetic TTL; source-owned review boundary",
  "correction_contract": "new decision supersedes prior projection",
  "escalation_or_close_path": "chairman_refuses",
  "source_refs": ["Mastermind@<sha>"]
}
```

For `INTENTIONAL_WAIT`, `owner_or_authority` names the durable non-Chairman owner and
`release_transition_ids` names the modeled review/timeout/cancel transitions.

### 9.4 Outcome

```json
{
  "outcome_id": "done",
  "kind": "TERMINAL_SUCCESS",
  "guards": [{"variable": "phase", "op": "EQ", "value": "DONE"}],
  "owned_persistent_obligation_ids": [],
  "owned_persistent_resource_ids": [],
  "source_refs": ["Mastermind@<sha>"]
}
```

Closed outcome kinds:

```text
TERMINAL_SUCCESS
TERMINAL_REFUSAL
TERMINAL_CANCELLED
TERMINAL_FAILED_SAFE
RECURRING_PROGRESS
```

A terminal outcome cannot own non-persistent residue.

### 9.5 Environment assumption

```json
{
  "assumption_id": "chairman_eventually_returns",
  "kind": "EXTERNAL_EVENT_MAY_OCCUR",
  "transition_ids": ["chairman_approves", "chairman_refuses"],
  "required_for_property_ids": ["OPTION_TO_COMPLETE"],
  "source_refs": ["Mastermind@<sha>"]
}
```

An external event assumption does not create fairness or promise that a human will act. If a property
requires the assumption, the progress disposition remains `EXTERNALLY_GATED` or conditional.

### 9.6 Model gap

Use the exact shape in Section 5. No bare string gap is allowed.

### 9.7 Report additions

`mastermind.operation_assurance_report.v1` adds:

```text
model_analysis_verdict
source_applicability
abstraction_contract
current_projection_verdict
```

Each counterexample adds the fields in Section 4. Existing report fields remain.

## 10. Test-plan corrections

OLS-A1 tests must additionally kill these mutations:

1. remove `abstraction_contract` parsing;
2. allow `DECLARED_EXACT` + `AUTHOR_DECLARATION` to produce `REPORT_ONLY_PROCEED`;
3. treat an over-approximate counterexample as source-realizable;
4. allow an under-approximate no-counterexample result to become proof;
5. let an unrelated non-load-bearing gap hide a source-validated counterexample;
6. let a relevant load-bearing gap leave a witness operationally certain;
7. conflate immutable `model_analysis_verdict` with current source applicability;
8. treat telemetry alone as `RUNTIME_REPLAY_CONFIRMED`;
9. search only closed SCCs and miss an unfair spin cycle with an outgoing finish edge;
10. accept a gate with no release transition or terminal assessment boundary;
11. permit an unknown `preserves`, fidelity, validation, realizability or applicability enum;
12. allow strong fairness in OLS-A1.

The safe finite fixture remains `PROVEN_WITHIN_FINITE_MODEL` for its declared model, with:

```text
source_applicability = AUTHOR_DECLARED_ONLY
admission_recommendation = REPORT_ONLY_NO_RECOMMENDATION
```

The model-only effect-unknown fixture remains `UNSAFE_COUNTEREXAMPLE` within its declared exact
model, with:

```text
realizability = DECLARED_MODEL_ONLY
admission_recommendation = REPORT_ONLY_REPAIR
repair_scope = MODEL_OR_DECLARED_CONTRACT
```

## 11. Research basis

This correction follows the established counterexample-guided abstraction-refinement boundary:
finite abstract models can produce spurious counterexamples, and those traces must be validated
against the concrete/source system before they are treated as implementation-real. It also preserves
the original workflow-net, TLA+/fairness, SPIN shortest-trace/liveness-cycle, Apalache finite-domain,
and Alloy lasso/bounded-horizon findings.

Load-bearing primary sources:

- E.M. Clarke, O. Grumberg, S. Jha, Y. Lu, and H. Veith,
  “Counterexample-Guided Abstraction Refinement for Symbolic Model Checking,” JACM 50(5), 2003.
- Carnegie Mellon MAGIC project, finite extracted models with counterexample validity checking and
  refinement to eliminate spurious traces.
- Leslie Lamport, PlusCal Tutorial Session 9, explicit weak/strong fairness semantics.
- Gerard J. Holzmann, SPIN verifier documentation, shortest BFS safety traces and non-progress/
  acceptance-cycle liveness analysis.

## 12. Final correction ruling

The OLS architecture remains accepted with these stronger boundaries:

> The checker proves or refutes properties of a declared finite model. A separate, explicit
> abstraction contract states what that model preserves about canonical source behavior. Every
> witness states its realizability. Current source applicability is orthogonal to the immutable
> model-analysis result. Only source-attested, property-preserving models may later support even a
> report-only operational proceed recommendation.

This amendment is a release blocker for OLS-F0. OLS-A1 must implement it from its first parser/report
commit rather than retrofitting fidelity after counterexamples exist.
