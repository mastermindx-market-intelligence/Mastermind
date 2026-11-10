# Mastermind Operation Liveness & Soundness Law

**Authority:** Chairman-directed Mastermind meta-control architecture.  
**Owner:** Sol, AI CEO of Mastermind-X.  
**Operation:** `mastermind-operation-liveness-soundness-20260830-sol-001`.  
**Original architecture basis:** `mastermindx-market-intelligence/Mastermind@28d365cceaef6efb0a26e0ac9af51ead44695d60`.  
**Protected reconciliation at drafting:** `mastermindx-market-intelligence/Mastermind@990b5b6c10ca9acb2f5fa42405c688c3b2abe2fc` (later protected reconciliations are pinned in the PR #279 release target).  
**Skillpack:** `mastermind.sol_skillpack.v1` v1.0.1 / bootstrap-major 1.  
**Status:** `SPEC_ONLY / RECORDS_ONLY / PRODUCTION_INERT` until this source law is protected.  
**Detailed design:** `docs/superpowers/specs/2026-08-30-operation-liveness-soundness-design.md`.  
**Executable A1 plan:** `docs/superpowers/plans/2026-08-30-operation-assurance-core.md`.

## CONTROLLING OLS-A1 IMPLEMENTATION NOTICE

The law, design, and original plan preserve the architecture and research history, but portions of
their earlier examples are historical drafting residue. A worker must **do not implement** an older
example where it conflicts with the following sources. Read them in this exact precedence order:

1. `docs/superpowers/specs/2026-08-31-operation-assurance-a1-wire-release-finalization.md`
   (wins on the exact immutable report field list, implementation navigation, the OLS-F0 release
   gate, external-auditor placement removal, and the Steward predecessor state)
2. `docs/superpowers/specs/2026-08-30-operation-assurance-immutable-report-projection-clarification.md`
3. `docs/superpowers/specs/2026-08-30-operation-assurance-model-fidelity-counterexample-validation-amendment.md`
4. `docs/superpowers/specs/2026-08-30-operation-assurance-a1-trusted-input-total-proof-clarification.md`
5. `docs/superpowers/specs/2026-08-30-operation-assurance-a1-controlling-execution-overlay.md`

Current adjacent-owner reconciliations are also mandatory:

- `docs/superpowers/specs/2026-08-31-operation-liveness-soundness-executive-steward-reconciliation.md`
- `docs/superpowers/specs/2026-08-31-operation-liveness-soundness-sol-capability-fabric-reconciliation.md`
- `docs/superpowers/specs/2026-08-30-operation-liveness-soundness-runtime-observability-reconciliation.md`

The precedence notice changes no runtime authority. It gives a fresh implementer one unambiguous
entry path into the current contract.

## 1. Chairman outcome

Before Mastermind trusts or expands a meaningful autonomous operation, it must be able to answer:

> Under the exact finite model, source snapshot, bounds, fairness assumptions, and external
> assumptions declared for this assessment, is there a reachable organizational black hole or
> progress violation? If so, what is the shortest actionable counterexample?

The target includes deadlock, livelock, ownerless obligations, stranded parents, stale or conflicting
action targets, unsafe retry or failover after ambiguous effects, terminal residue, resource cycles,
carrier splits, starvation, and false-green projections. It must also preserve valid capacity
parking, natural or calendar waits, recurring services, safe cancellation, and genuine Chairman or
external gates.

Operation Assurance is not a universal theorem about future reality. It is a deterministic,
source-attributed result over a declared finite abstraction whose limits remain visible.

## 2. Canonical architecture

The canonical analytical object is a closed finite labelled transition system:

```text
mastermind.operation_assurance_model.v1
```

The first executable vertical is:

```text
authored closed model
-> exact structural and semantic validation
-> deterministic breadth-first reachable-state exploration
-> safety and workflow-soundness analysis
-> all reachable cyclic-SCC analysis
-> weak-fair closed-walk search
-> recurring-progress and starvation analysis
-> shortest deterministic source-attributed counterexample
-> mastermind.operation_assurance_report.v1
-> report-only CLI
```

The checker is a pure analytical consumer. The model and report are immutable values, not lifecycle,
authority, routing, placement, retry, source, or product stores.

Workflow-net soundness contributes option-to-complete, proper-completion, and no-dead-transition
properties. Temporal model checking contributes the safety/liveness split, explicit fairness, and
prefix + cycle witnesses. Neither formalism alone becomes Mastermind's product contract. The
accepted architecture is a closed domain-specific transition model with deterministic explicit-state
checking and optional later independent formal exports.

## 3. Canonical owner preservation

| Concern | Existing canonical owner | Operation Assurance relationship |
|---|---|---|
| Job / Attempt / Worker / Event lifecycle, admission, leases, fences, retry, requeue, effect state | Executive OS | Read-only evidence; never mutate or reinterpret ownership |
| durable workstream, decision, discovery, dependency, wait, and handoff identity | Agent OS | Read structured records; never become Agent OS |
| canonical company dialogue and semantic turns | Agent Dialogue / Company Dialogue | Read-only carrier evidence; never create another transcript plane |
| attention obligation, delivery, ACK, and source resolution | Executive Inbox / Wake | Read-only evidence; never schedule or deliver Wake |
| current action target and provider-session binding | SessionTarget/RuntimeBinding | Consume exact source-owned identity; never elect or transfer |
| eligibility, quota, and placement | Capacity Fabric / Model Router | Read-only evidence; never allocate or reserve |
| normalized cross-owner composition | corrected Executive Steward / OCR-6 | Reuse the protected pure read core and later accepted gather seam; never fork it |
| product explanation and interaction | Chairman Control Room | Consumer only; no new assurance truth store |
| executive attention pressure and serviceability | Executive Attention Frontier | May consume typed assurance evidence later; Operation Assurance never ranks demand |
| implementation, commits, PRs, checks, and immutable evidence | GitHub | Canonical implementation truth |
| selected portfolio projection | Linear | Projection only |
| transport and hot-state visibility | Slack / Agent Relay | Transport only |

Forbidden replacements include an assurance-owned lifecycle, queue, scheduler, watcher registry,
retry service, authority store, session registry, worker registry, transcript store, capacity
allocator, attention allocator, source graph, GitHub mirror, observability store, or second Steward.

## 4. Closed truth axes

The immutable report keeps independent axes rather than collapsing them into one green/red field.

### 4.1 Model-analysis verdict

```text
UNSAFE_COUNTEREXAMPLE
PROVEN_WITHIN_FINITE_MODEL
BOUNDED_NO_COUNTEREXAMPLE
INCONCLUSIVE_MODEL_GAP
```

`PROVEN_WITHIN_FINITE_MODEL` means the complete reachable state space and every load-bearing
analysis product completed under the declared finite model and assumptions. It is not a proof that
the model is current or perfectly faithful to production.

`BOUNDED_NO_COUNTEREXAMPLE` means only that no violating witness was found inside published bounds.
It must never be rendered as proved safe.

`INCONCLUSIVE_MODEL_GAP` preserves an unsupported construct, fidelity problem, relevant model gap,
incomplete analysis, or potentially spurious witness without manufacturing a pass.

### 4.2 Source applicability at generation

```text
AUTHOR_DECLARED_ONLY
CURRENT_SOURCE_ATTESTED
HISTORICAL_SOURCE_ATTESTED
STALE
CONFLICTED
INCOMPLETE
UNKNOWN
```

OLS-A1 is fixed to authored input. Positive labels inside authored JSON cannot grant current source
attestation or replay authority. Negative source facts may only weaken the result.

### 4.3 Abstraction fidelity

```text
DECLARED_EXACT
SOUND_OVERAPPROXIMATION
TRACE_BACKED_UNDERAPPROXIMATION
HEURISTIC_ABSTRACTION
UNKNOWN_FIDELITY
```

Every model declares what properties its abstraction preserves and what behavior may have been
introduced or excluded. Model prose has zero authority.

### 4.4 Counterexample realizability

```text
DECLARED_MODEL_ONLY
SOURCE_CONTRACT_VALIDATED
RUNTIME_REPLAY_CONFIRMED
POTENTIALLY_SPURIOUS
INVALIDATED
```

A model witness is never silently promoted to production truth. Telemetry alone cannot produce
semantic runtime replay confirmation.

### 4.5 Current derived status

`MODEL_STALE_OR_INVALID` is a later current read-projection status, not an immutable model-analysis
verdict. Corrected Steward / Control Room may derive it from an immutable report plus current source
receipts without rewriting the report.

### 4.6 Progress disposition and recommendation

The immutable generation-time report also records one progress disposition and one report-only
recommendation. These are analytical outputs, not current authority:

```text
AUTONOMOUSLY_LIVE
FAIRNESS_CONDITIONAL
EXTERNALLY_GATED
INTENTIONAL_WAIT
RECURRING_SERVICE
NO_PROGRESS
UNKNOWN
```

```text
REPORT_ONLY_REPAIR
REPORT_ONLY_RECONCILE
REPORT_ONLY_AWAIT_GATE
REPORT_ONLY_NO_RECOMMENDATION
```

OLS-A1 never emits `REPORT_ONLY_PROCEED`. V1 is report-only. No report value creates, blocks,
cancels, retries, requeues, wakes, places, merges, or admits an Executive operation.

## 5. Closed model contract

Every `mastermind.operation_assurance_model.v1` contains exactly the reviewed top-level fields:

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

The property set is:

```text
mastermind.operation_assurance.properties.v1
```

All domains are finite and non-empty. Guards and effects use a closed grammar. Transition effects are
simultaneous assignments. Unknown keys, duplicate identities, duplicate effects for one variable,
non-finite values, values outside declared domains, unresolved or one-sided references, executable
predicates, and unsupported fairness fail closed during parsing.

Caller-supplied compiler names, freshness labels, validation kinds, validation refs, timestamps, or
source refs are descriptive input only in A1. They cannot mint trusted evidence.

## 6. Required property families

The checker owns mandatory built-in coverage. Authored property lists cannot suppress it.

### 6.1 Identity and authority safety

- one modifying logical operation has one carrier until canonical reconciliation;
- a sanctioned transition has a current eligible actor and exact required binding;
- one unresolved semantic turn has at most one action-authoritative Sol target;
- stale, conflicting, or absent identity cannot authorize a transition.

### 6.2 Effect and retry safety

`EFFECT_UNKNOWN` cannot escape through retry, rerun, requeue, alternate provider, alternate host,
alternate account, alternate session, alternate carrier, or a second modifying effect before the
canonical owner reconciles it.

### 6.3 Workflow soundness

- every relevant reachable state retains an option to complete, enter a valid wait/gate, or produce
  accepted recurring progress;
- proper terminal completion leaves no unowned non-persistent obligation, held resource, live child,
  open carrier turn, or ambiguous effect;
- every transition marked required-reachable is reached;
- adverse exits are explicit terminal refusal, safe cancellation, or safe failure outcomes.

### 6.4 Terminal absorption

Every reached terminal outcome is absorbing under the built-in property:

```text
NO_POST_TERMINAL_TRANSITION
```

Recurring progress is not terminal completion.

### 6.5 Whole-operation progress

The checker evaluates synthetic root progress even when an authored model contains no explicit
obligation. A reachable fairness-valid non-progress lasso is a violation unless it is a valid
modeled gate, intentional wait, or recurring service.

### 6.6 Fairness and starvation

OLS-A1 supports no-fairness and weak fairness only. Strong fairness is outside OLS-A1. Weak fairness
may exclude a candidate closed walk only when the named transition is enabled in every visited cycle
state and never taken.

The search is not limited to a simple cycle or a closed SCC. It examines all reachable cyclic SCCs
and uses an augmented seen-or-disabled fairness product so a valid witness may combine simple cycles.
Fairness assumptions must themselves be realizable; a vacuous assumption cannot manufacture
liveness.

### 6.7 Total proof completion

A drained base BFS queue is necessary but insufficient for proof. Safety, reverse completion,
proper-completion, required-transition reachability, SCC discovery, every fairness product,
recurring-progress analysis, and starvation analysis must all finish. A checker exception, timeout,
state limit, product limit, unsupported construct, or internal validation failure can only weaken or
refuse the result. It can never produce a pass.

A fully materialized definite witness is not erased merely because an unrelated later analysis hits
a declared bound.

## 7. Valid waits and external gates

A nonterminal state is not a deadlock merely because Mastermind cannot advance autonomously. A valid
wait or gate has a typed disposition, accountable owner or authority, machine-observable release
condition, source-relative time behavior, correction behavior, and explicit release, review,
escalation, cancellation, refusal, or lawful-closure transitions.

Descriptive prose such as “wait for Chairman” is not a return path. A terminal assessment boundary is
represented by a transition reaching a named terminal outcome; transitionless terminal-boundary
claims are refused.

Capacity unavailable with no lawful receiver is valid parking only when existing Capacity/runtime
owners represent the wait and a lawful re-entry or closure transition exists. It grants no account
hopping or implicit failover.

## 8. Counterexample contract

Every failed property produces one shortest deterministic actionable witness. A liveness witness is
a prefix + cycle. The closed content includes:

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
minimal deterministic repair candidates
limitations
```

The controlling immutable-report clarification additionally freezes `witness_kind`
(`TRACE / LASSO / GLOBAL_CERTIFICATE`) and `initial_state`; its exact counterexample field list wins
over this summary.

Safety prefixes use breadth-first distance and canonical transition ordering. Liveness lassos use the
shortest reachable prefix, shortest fairness-valid violating closed walk, canonical transition
sequence, and state fingerprint tie-breaks. The report keeps enough enabled and disabled transition
reasons to show why the operation became stuck or could avoid progress forever.

A language model may explain a deterministic witness after generation. It may not create, suppress,
upgrade, rank, or override a verdict, source receipt, realizability state, or repair precondition.

## 9. Time, correction, and immutable identity

Every load-bearing source receipt identifies its owner, resource, exact revision, content digest,
coverage, observation/effective time where owned, and correction or supersession identity. Time never
substitutes for revision. Missing, stale, partial, contradictory, or truncated evidence remains typed
uncertainty.

The immutable report hash is computed over the canonical report body excluding `report_id` and
`report_hash`. `report_id` is then derived from that hash. Wall-clock duration is excluded from the
canonical report; deterministic work counts belong in the exploration receipt.

A later correction never rewrites or re-hashes an old report. Current status is a separate read
composition.

## 10. Product experience

The eventual Chairman Control Room card explains:

- model verdict, source applicability, abstraction fidelity, and witness realizability;
- progress disposition and report-only recommendation;
- exact source snapshot and current applicability;
- complete versus bounded exploration and every limit reached;
- fairness and environment assumptions;
- mandatory property coverage and gaps;
- shortest source-attributed counterexample timeline;
- unresolved owner, resource, effect, target, Wake, carrier, or parent-continuation fact;
- proposed repair and before/after reassessment;
- report supersession and runtime-conformance evidence.

Required states include checking, finite-model proof, bounded-only, inconclusive, counterexample,
externally gated, intentional wait, recurring service, stale, superseded, source unavailable, and
checker refusal. Bounded, stale, or inconclusive results cannot be visually presented as safe.

## 11. Adjacent programs and current boundaries

- Executive Attention Frontier asks which valid demand deserves cognition; it never ranks from an OLS
  verdict alone, and Operation Assurance never ranks demand.
- PR #268 owns watcher self-deadlock hardening. It is a hostile-case source, not an OLS owner.
- PR #228 is now protected as the pure Executive Steward read core. The current relationship is
  frozen in `2026-08-31-operation-liveness-soundness-executive-steward-reconciliation.md`.
- Operation Assurance must not create a parallel federated reader. A2 reuses Steward plus a separately
  accepted bounded gather/source-compiler seam.
- Sol Capability Fabric owns normalized GitHub status, release assessment, prepared action, effect
  receipt, and runner explanation.
- Runtime Observability owns diagnostic collection; a complete trace is not liveness proof and a
  missing trace is not a deadlock proof.
- Project Workroom remains a collaboration projection and grants no assurance authority.
- Worker Browser B1 is path-disjoint product tooling and changes no OLS proof semantics.

## 12. Implementation and promotion sequence

1. **OLS-F0:** protect this architecture, exact precedence, owner boundaries, and executable plan.
2. **OLS-A1:** build the pure parser/checker/report/CLI vertical with hostile fixtures.
3. **OLS-A1R:** direct adversarial CEO review plus mutation tests and exact-head hosted CI.
4. **OLS-A2:** compile one source-attributed operation through the accepted Steward/gather seam.
5. **OLS-A3:** compose immutable report and current status in existing Steward / Control Room owners.
6. **OLS-A4:** calibrate against historical and hostile cases, including valid waits.
7. **OLS-A5:** run a report-only operational canary that changes a repair decision without granting
   enforcement authority.
8. **OLS-A6:** verify runtime-model conformance using canonical events plus bounded diagnostic evidence.
9. **OLS-G1:** only after prospective evidence, propose any narrow promotion gate as a separate law.

## 13. Release and completion law

F0 release requires a single current carrier, exact protected-base preservation, exact-head hosted
checks, no unresolved review thread, direct Program-CEO adversarial review against Chairman intent,
and an expected-head merge. A separate Auditor Sol placement is not a release prerequisite.

Green CI proves the source/test gate, not implementation, runtime conformance, production proof, or
final acceptance.

> Protecting OLS-F0 makes only the architecture and no-rebuild law true.

It does not build or prove the checker, compiler, product, admission integration, runtime conformance,
or canary. Program completion requires truth, intelligence, product, and learning: a current source
compiler, deterministic checker, useful Control Room workflow, calibrated false-positive/negative
performance, and a real report-only canary whose operational outcome is observable.
