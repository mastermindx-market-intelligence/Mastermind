# Operation Assurance A1 — Trusted Input, Terminality, and Total-Proof Clarification

**Status:** NARROW CONTROLLING CLARIFICATION / SPEC_ONLY / RECORDS_ONLY / PRODUCTION_INERT  
**Date:** 2026-08-30  
**Owner:** Sol, AI CEO of Mastermind-X  
**Operation:** `mastermind-operation-liveness-soundness-20260830-sol-001`  
**Protected source reconciled:** `mastermindx-market-intelligence/Mastermind@620263090fb9f272f763e420ba103b0ff8dc5f31`  
**Parent execution overlay:** `docs/superpowers/specs/2026-08-30-operation-assurance-a1-controlling-execution-overlay.md`

This clarification closes four proof-inflation and model-authority gaps found during adversarial
Program-CEO review after the controlling OLS-A1 execution overlay was written. It does not create a
new architecture, checker, lifecycle, source compiler, evidence validator, runtime integration, or
admission gate.

Where this clarification conflicts with the parent execution overlay on the four subjects below,
this clarification wins. The immutable-report clarification and model-fidelity amendment remain the
higher wire authorities. All other OLS-A1 boundaries remain unchanged.

## 1. Authored input has no trusted-evidence authority

A1 invocation authority is fixed to AUTHORED_INPUT.

The OLS-A1 CLI accepts an authored closed model for deterministic analysis. The authored document may
carry future-facing source, compiler, fidelity, and validation fields so the schema remains compatible
with later compiler and replay waves, but those fields are descriptive assertions only inside A1.

The controlling anti-forgery rule is:

> caller-supplied compiler names, freshness values, validation_kind, validation_refs, or source_refs never grant CURRENT_SOURCE_ATTESTED and never grant SOURCE_CONTRACT_VALIDATED or RUNTIME_REPLAY_CONFIRMED.

A1 may preserve negative source information supplied by a hostile fixture—such as `STALE`,
`CONFLICTED`, `INCOMPLETE`, or `UNKNOWN`—because that can only weaken applicability or force
reconciliation. Positive labels cannot upgrade the result above `AUTHOR_DECLARED_ONLY` or
`DECLARED_MODEL_ONLY` merely because the JSON contains authoritative-looking strings.

Therefore:

- `SOURCE_COMPILER_ATTESTATION` in an authored file does not prove a source compiler ran;
- `SOURCE_CONTRACT_REPLAY` in an authored file does not prove the trace was validated;
- `RUNTIME_EVENT_REPLAY` in an authored file does not prove canonical events were replayed;
- a Git SHA, source ref, validation ref, or current timestamp is evidence identity text, not evidence
  authority;
- telemetry identifiers never create semantic replay authority;
- model prose, comments, filenames, or CLI flags cannot promote applicability or realizability.

trusted evidence upgrades are outside OLS-A1. They require a separately accepted, unforgeable
invocation boundary owned by the canonical OLS-A2 source compiler or a later deterministic source or
runtime replay validator. A future trusted caller must pass evidence through a typed host-owned API or
capability not expressible by the authored model document itself.

### 1.1 A1 normalization

For ordinary authored input, the checker normalizes positive evidence axes as follows:

```text
source_applicability_at_generation = AUTHOR_DECLARED_ONLY
counterexample.realizability       = DECLARED_MODEL_ONLY
```

An over-approximate, heuristic, unknown-fidelity, or relevant-gap witness remains
`POTENTIALLY_SPURIOUS` according to the existing fidelity law. Negative source facts can further
weaken applicability. No authored field can strengthen either axis.

### 1.2 Required falsifiers

Tests must fail if implementation:

1. trusts a caller-supplied compiler name or version as source attestation;
2. trusts `freshness=FRESH` as current canonical applicability;
3. trusts `validation_kind=SOURCE_CONTRACT_REPLAY` as replay evidence;
4. trusts `validation_kind=RUNTIME_EVENT_REPLAY` as runtime confirmation;
5. treats validation or source references as capability tokens;
6. exposes an A1 CLI switch that claims trusted compiler or replay mode.

## 2. Terminal outcomes are absorbing

A terminal outcome is the accepted end of one finite operation execution. It cannot simultaneously
be a state from which further operation transitions remain enabled.

The checker therefore evaluates the built-in property:

```text
NO_POST_TERMINAL_TRANSITION
```

For every reached state matching one or more terminal outcomes, no transition may be enabled from a terminal outcome state.

A violation is a concrete safety/workflow counterexample. It identifies the terminal outcome IDs,
enabled transition IDs, source refs, and shortest prefix to the terminal state. Terminal overlap is
allowed only when every matching outcome has compatible terminal semantics and the state is
absorbing; ambiguous incompatible terminal classification fails closed.

Implicit logical stuttering used by model-checking semantics is not an executable operation
transition. It creates no actor action, effect, retry, Wake, carrier write, or lifecycle event.

recurring outcomes are not terminal outcomes. A recurring service is analyzed using its named
recurring-progress outcome, persistent obligations/resources, and liveness/starvation properties. It
must not be converted into a fake terminal state merely to avoid cycle analysis.

### 2.1 Required falsifiers

Tests must fail if implementation:

1. ignores an enabled retry, cleanup, failover, modify, or progress transition after terminal match;
2. silently drops the post-terminal transition from the graph;
3. treats a recurring progress outcome as terminal;
4. lets a terminal state own non-persistent residue;
5. chooses one of conflicting terminal outcomes by input order.

## 3. Proof requires total completion of every load-bearing analysis

A complete base reachable graph proves only that base-state enumeration finished. It does not prove
that every load-bearing property analysis, augmented product, or witness search also completed.

The controlling rule is exact:

> a complete reachable graph is necessary but not sufficient for proof; fairness-product, option-to-complete, proper-completion, dead-transition, safety, and starvation analyses must all be complete.

`PROVEN_WITHIN_FINITE_MODEL` is legal only when all of the following are true:

- parser and cross-reference validation completed normally;
- the full reachable base state graph completed within declared limits;
- every declared and built-in safety property completed;
- reverse option-to-complete analysis completed;
- proper-completion checks covered every reached terminal outcome;
- required-transition reachability completed;
- all cyclic-SCC discovery completed;
- every required fairness-valid closed-walk search completed;
- recurring-progress and starvation searches completed;
- every property result is `PASS` or an explicitly valid `NOT_APPLICABLE` under the closed property
  contract;
- no load-bearing model gap affects a proved property;
- the abstraction contract preserves every property claimed by the proof;
- the checker terminated normally without internal exception.

The existing `max_states` limit also bounds each augmented fairness-product or property-product
search. A product search that reaches the bound records:

```text
FAIRNESS_PRODUCT_STATE_LIMIT_REACHED
```

The exploration receipt and property result must make the incomplete product visible. A future schema
may add separate reviewed product limits, but A1 cannot invent hidden unlimited work or silently stop
searching.

The verdict law distinguishes incomplete no-witness analysis from an already complete unsafe
witness:

> without a fully materialized definite witness, analysis exhaustion yields BOUNDED_NO_COUNTEREXAMPLE or INCONCLUSIVE_MODEL_GAP, never proof.

> resource-bound exhaustion does not erase a fully materialized definite counterexample.

A fully materialized witness means the complete prefix or lasso, failed property, state deltas,
source references, realizability classification, and relevant-gap check were all deterministically
constructed before the bound was reached. Such a witness remains `UNSAFE_COUNTEREXAMPLE` within its
existing fidelity and applicability scope even when unrelated later exploration is incomplete.

A checker internal exception is different from an ordinary declared resource bound: a checker internal exception never upgrades a result and may require bounded report refusal. If the exception occurs after a
fully materialized witness and the immutable report can still be validated and finalized through the
normal error boundary, the witness may remain visible; otherwise the CLI refuses the report rather
than emitting partially trusted output. An exception never becomes proof or a healthy default.

### 3.1 Required falsifiers

Tests must fail if implementation:

1. sets proof after the BFS queue drains while a fairness search was truncated;
2. treats an `UNKNOWN` property as pass;
3. omits a built-in property from the proof-coverage receipt;
4. catches an internal exception and returns proof or a healthy default;
5. hides which product or property exhausted its bound;
6. lets wall-clock timeout or memory pressure become a pass;
7. discards a complete definite counterexample merely because a later unrelated search reaches a
   declared resource bound;
8. emits a partially constructed witness after an internal exception.

## 4. Terminal gate boundaries must be machine represented

The earlier gate law allows a modeled release path or a terminal assessment boundary. A terminal
assessment boundary is not free-form text and is not permission to stop modeling at an arbitrary
human wait.

OLS-A1 does not accept a transitionless terminal-boundary claim.

For A1, a terminal assessment is represented by a release_transition_id leading to a named terminal outcome. The release transition may represent refusal, safe cancellation, bounded assessment close,
or another explicitly accepted adverse terminal path. Its guard must match the gate state, its effects
must reach the terminal outcome guard, and its source refs must identify the governing gate contract.

The gate’s `release_condition` must describe the machine-observable condition associated with one or
more `release_transition_ids`. The field escalation_or_close_path must name one of the release_transition_ids. A sentence such as “Chairman decides later” or “stop at external authority” is not
machine binding.

A syntactically complete gate that lacks a realizable release transition to a terminal or continuing
state remains `EXTERNAL_GATE_INCOMPLETE` or `INTENTIONAL_WAIT_INCOMPLETE` as appropriate. Missing
required gate fields remain parser refusal. These are distinct failure classes.

### 4.1 Required falsifiers

Tests must fail if implementation:

1. accepts a gate whose `release_transition_ids` is empty;
2. accepts a release transition that cannot be enabled in the gate state;
3. accepts a terminal-boundary label with no named terminal outcome reached by effects;
4. accepts `escalation_or_close_path` as arbitrary prose;
5. treats an environment assumption as a promise that a human eventually acts;
6. calls an incomplete gate a valid wait merely because it has an accountable owner.

## 5. Task-level implementation consequences

### Parser

- Fix A1 invocation mode to `AUTHORED_INPUT`; do not read a trust level from the model.
- Preserve closed future-facing fields but normalize positive applicability and realizability to the
  A1 ceiling.
- Validate gate release and close references bidirectionally.
- Reject transitionless terminal-boundary claims.

### Reachability and workflow soundness

- Evaluate `NO_POST_TERMINAL_TRANSITION` for every reached terminal state.
- Keep recurring outcomes separate from terminal outcomes.
- Include terminal overlap and absorption in deterministic property ordering.

### Liveness and fairness

- Track product-search completeness separately from base-graph completeness.
- Apply the declared state bound to augmented products and expose the exact limit reason.
- Preserve fully materialized definite witnesses while refusing incomplete global proof.

### Immutable report

- Include per-property completion and coverage sufficient to show that all load-bearing analyses ran.
- Never serialize caller claims as stronger trusted evidence.
- Keep generation-time applicability, model verdict, progress disposition, and recommendation
  orthogonal.
- Refuse partial output when an internal error prevents full immutable-report validation.

### CLI

- Accept only authored model input; no trusted-source or trusted-replay flags exist.
- Invalid input returns the bounded refusal exit.
- Valid unsafe, bounded, or inconclusive reports still return normal report completion and JSON.
- Internal checker failure returns the bounded checker-refusal exit unless a fully validated report
  was already finalized.

## 6. Capability and no-rebuild boundary

This clarification is records-only. It creates no source compiler, replay service, credential,
capability token, lifecycle, event, queue, scheduler, watcher, retry, carrier, RuntimeBinding,
Capacity selector, Steward, Control Room store, telemetry plane, or admission enforcement.

Protecting it makes only the A1 trust ceiling, terminal absorption, total-proof completion rule, and
machine-represented gate boundary durable. OLS-A1 remains authored-input, pure,
standard-library-only, report-only, and production-inert. Trusted compilation, current status,
runtime replay, Control Room composition, admission attachment, conformance, canary, and enforcement
remain later separately accepted waves.
