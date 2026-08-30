# Mastermind Operation Liveness & Soundness Law

**Authority:** Chairman-directed Mastermind meta-control architecture.  
**Owner:** Sol, AI CEO of Mastermind-X.  
**Operation:** `mastermind-operation-liveness-soundness-20260830-sol-001`.  
**Protected source at freeze:** `mastermindx-market-intelligence/Mastermind@28d365cceaef6efb0a26e0ac9af51ead44695d60`.  
**Skillpack:** `mastermind.sol_skillpack.v1` v1.0.1 / bootstrap-major 1.  
**Status:** `SPEC_ONLY / RECORDS_ONLY / PRODUCTION_INERT`.  
**Detailed design:** `docs/superpowers/specs/2026-08-30-operation-liveness-soundness-design.md`.  
**Program plan:** `docs/superpowers/plans/2026-08-30-operation-assurance-core.md`.

This law defines how Mastermind may reason about the progress safety of a proposed or running
autonomous operation. It creates no Job, Attempt, Worker, Event, queue, scheduler, retry, Wake,
RuntimeBinding, session, authority grant, admission gate, provider call, Control Room mutation, or
new persistence plane.

## 1. Chairman outcome

Before Mastermind trusts a meaningful autonomous operation to run or expands its child graph, it
must be able to answer:

> Under the exact finite model, source snapshot, bounds, fairness assumptions, and external
> assumptions declared for this assessment, is there a reachable organizational black hole or
> progress violation? If so, what is the shortest actionable counterexample?

The target includes deadlock, non-progress cycles, ownerless obligations, stranded parents,
unserviceable action targets, unsafe retry/failover after ambiguous effects, terminal residue,
resource cycles, and starvation under declared fairness. It must preserve valid capacity parking,
typed natural/calendar waits, recurring services, and genuine Chairman or external gates rather
than misclassifying them as deadlock.

The product is not a universal theorem about future reality. It is a source-attributed assurance
result over a declared abstraction.

## 2. Core architecture ruling

The canonical analytical object is a closed, versioned, finite labelled transition system:

```text
mastermind.operation_assurance_model.v1
```

It is compiled from existing canonical owners or supplied as a source-attributed design-time model.
It is an analysis-only value. It is never a lifecycle record and never an authority source.

The first checker implementation uses deterministic explicit-state exploration and graph analysis in
pure Python:

```text
closed model
-> structural and semantic validation
-> breadth-first reachable-state exploration
-> strongly connected component / lasso analysis
-> property evaluation
-> minimal source-attributed counterexample
-> mastermind.operation_assurance_report.v1
```

A workflow-net/Petri-net projection may be produced later as a diagnostic or independent audit
backend. It is not the canonical model. TLA+, SPIN, Alloy, Apalache, SMT, or another formal backend
may later independently validate selected models, but no external verifier is a V1 runtime
dependency or a replacement for the Mastermind source compiler.

## 3. Proof-language boundary

Mastermind uses the following closed assurance verdicts:

```text
UNSAFE_COUNTEREXAMPLE
PROVEN_WITHIN_FINITE_MODEL
BOUNDED_NO_COUNTEREXAMPLE
INCONCLUSIVE_MODEL_GAP
MODEL_STALE_OR_INVALID
```

The verdict is separate from progress disposition:

```text
AUTONOMOUSLY_LIVE
FAIRNESS_CONDITIONAL
EXTERNALLY_GATED
INTENTIONAL_WAIT
RECURRING_SERVICE
NO_PROGRESS
UNKNOWN
```

The verdict is also separate from admission recommendation:

```text
REPORT_ONLY_PROCEED
REPORT_ONLY_REPAIR
REPORT_ONLY_RECONCILE
REPORT_ONLY_AWAIT_GATE
REPORT_ONLY_NO_RECOMMENDATION
```

V1 is report-only. None of these values blocks, creates, retries, requeues, cancels, wakes, places,
fails over, or admits an Executive operation.

`PROVEN_WITHIN_FINITE_MODEL` is legal only when all declared domains are finite, the complete
reachable state space was explored, no load-bearing source is missing/conflicting/stale, no opaque
guard or transition remains, all assumptions are enumerated, and the checker terminated normally.

`BOUNDED_NO_COUNTEREXAMPLE` means only that no violating trace was found within the published state,
depth, or resource bounds. It must never be rendered as proved safe.

A checker exception, timeout, state limit, unsupported construct, unresolved source join, or
unbounded domain can only weaken the result to `BOUNDED_NO_COUNTEREXAMPLE`,
`INCONCLUSIVE_MODEL_GAP`, or `MODEL_STALE_OR_INVALID`. It can never produce a pass.

## 4. Canonical owner preservation

| Concern | Existing canonical owner | Operation Assurance relationship |
|---|---|---|
| Job / Attempt / Worker / Event lifecycle, admission, leases/fences, retry/requeue, effect state | Executive OS | Read only; never mutate or reinterpret lifecycle |
| durable program/workstream/decision/discovery/handoff/dependency/wait identity | Agent OS | Read structured records; never become Agent OS |
| canonical dialogue parent/messages/semantic turns | Agent Dialogue / Company Dialogue | Read only; never create another carrier or transcript store |
| attention obligation, delivery, ACK and source resolution | Executive Inbox / Wake | Read only; never schedule or deliver Wake |
| exact current Sol action target | `sol_action_target` plus SessionTarget/RuntimeBinding owners | Consume exact result when live; never elect, promote or transfer |
| provider/account/host eligibility and capacity | Capacity Fabric / Model Router | Read only; never place or reserve capacity |
| normalized cross-owner read | corrected Executive Steward / OCR-6 | Primary production source compiler seam after protection |
| product composition | Chairman Control Room | Consumer only; no assurance database |
| attention prioritization | Executive Attention Frontier | May consume typed assurance/serviceability evidence later; assurance never ranks |
| implementation/evidence | GitHub | Canonical code, PR, CI and immutable proof |
| selected portfolio projection | Linear | Projection only |
| transport/hot state | Slack / Agent Relay | Transport only |

Forbidden replacements include an assurance lifecycle, liveness queue, scheduler, watcher registry,
retry service, authority store, session registry, worker registry, transcript store, capacity
allocator, attention allocator, source-of-truth graph, or second Steward.

## 5. Closed model contract

The detailed wire is frozen in the design, but every V1 model must include:

```text
schema
model_id
operation_ref
root_job_id or explicit pre-admission identity
compiler_version
source_snapshot
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

Every transition has a stable identity, closed guard grammar, closed effect grammar, actor/authority
class, progress tags, and source references. Arbitrary Python, shell, SQL, regular expressions, or
model-generated executable predicates are forbidden in the wire.

All identities and arrays are canonicalized and deterministically ordered. State fingerprints,
model hashes, report hashes, and counterexample ordering are reproducible from canonical JSON.

Unknown or missing owner facts remain explicitly unknown. Null never means false, healthy, absent,
unlimited, available, or safe.

## 6. Property families

The checker evaluates separately named properties rather than one magic `sound=true` bit.

### 6.1 Identity and authority safety

- one logical operation has one canonical identity and, while modifying, one canonical carrier until
  reconciliation;
- sanctioned actions require a current eligible owner and exact current binding where the governing
  owner requires one;
- one unresolved semantic turn has at most one action-authoritative Sol target;
- stale or conflicting Attempt/Worker/RuntimeBinding evidence cannot authorize a transition.

### 6.2 Effect and retry safety

- `EFFECT_UNKNOWN` cannot transition to retry, requeue, alternate provider, alternate host, alternate
  session, alternate carrier, or a second modifying effect before canonical reconciliation;
- a retry-safe transition must name the typed source-owned retry class;
- transport loss, response loss, unknown failure, and ambiguous writer identity never imply retry
  safety.

### 6.3 Workflow soundness

For every reachable state not explicitly classified as a valid external gate, intentional wait, or
recurring-service state:

- **option to complete:** at least one lawful path reaches an accepted outcome;
- **proper completion:** accepted terminal outcomes leave no unresolved obligations, live children,
  leases, resources, carrier turns, or ambiguous effects;
- **no dead declared transitions:** every transition declared as required/usable is reachable unless
  explicitly disabled by design;
- **cancellation/failure completion:** lawful adverse exits are first-class outcomes, not hidden
  exceptions.

### 6.4 Progress and continuity

- an admitted nonterminal operation reaches a terminal outcome, valid external gate, valid
  intentional wait, or recurring progress state under the exact declared assumptions;
- a terminal child eventually yields parent continuation or lawful parent closure;
- every wait has an accountable owner, observable return condition, canonical carrier or source
  condition, correction behavior, and lawful escalation/closure;
- every acquired resource has a release or transfer path;
- every durable continuation obligation has a reachable consumer;
- a reachable closed non-progress strongly connected component is a livelock counterexample.

### 6.5 Starvation and fairness

Fairness is never silently assumed.

- weak fairness may be declared only for a transition that remains continuously enabled;
- strong fairness may be declared only when the source contract explicitly warrants eventual service
  for a transition enabled infinitely often;
- no-fairness, weak-fairness and strong-fairness results are distinct;
- a lasso in which an obligation remains pending forever is a starvation witness when it satisfies
  the model's transition semantics and violates the declared fairness contract.

The first implementation must support no-fairness and weak-fairness analysis. Strong-fairness
analysis is a separately reviewed later capability unless the first implementation proves a correct
closed algorithm and discriminating tests without widening its wave.

## 7. Valid waiting and external gates

A nonterminal state is not a deadlock merely because Mastermind cannot advance autonomously.

`INTENTIONAL_WAIT` requires all of:

```text
typed wait kind
accountable durable owner
observable release/review condition
source/effective/observation time behavior
correction behavior
lawful escalation or closure
```

`EXTERNALLY_GATED` additionally requires a named external or Chairman/admin authority and a defined
return path. A statement such as “waiting for Chairman” without a carrier/condition/owner is not a
valid gate.

Capacity unavailable with no lawful receiver is valid parking only when existing Capacity/runtime
owners can represent the wait and a lawful re-entry condition exists. It grants no manual
cross-account failover.

A persistent service is assessed through recurring progress or bounded-response obligations, not
forced terminal completion.

## 8. Counterexample contract

`UNSAFE_COUNTEREXAMPLE` must contain an actionable witness:

```text
property_id
model_hash
source_snapshot_hash
assumptions
exploration_receipt
shortest_prefix
cycle, when liveness/non-progress is involved
state_delta_per_step
enabled_and_disabled_transition_reasons
unresolved owner/resource/gate/effect/binding/wake/continuation
source_refs
minimal deterministic repair candidates
limitations
```

Safety prefixes are shortest under breadth-first search and deterministic transition ordering.
Liveness witnesses are deterministic lassos: a shortest reachable prefix to a violating component
plus a shortest reproducible cycle inside it, subject to the documented tie-break law.

A language model may explain the witness after generation. It may not create, suppress, upgrade, or
override the verdict, property result, source receipt, or repair precondition.

## 9. Time, freshness and correction law

Every load-bearing source receipt carries its canonical owner, source identity, schema/version,
content digest or immutable event identity, effective time where owned, observation time where
owned, and correction/supersession identity where available.

No universal freshness TTL is invented across Executive runtime, Git, Agent OS, Slack, external
calendar gates, and strategic decisions. The source owner defines freshness.

A report binds:

```text
model_hash
source_snapshot_hash
compiler_version
checker_version
property_set_version
exploration_limits
assumption_set
generated_at
```

A later correction never rewrites the old result as if it had used the corrected source. The old
report remains historical evidence and the current projection becomes `MODEL_STALE_OR_INVALID` until
a new report supersedes it.

## 10. Product and Control Room projection

The eventual Control Room card must explain, not merely color, the result:

- assurance verdict, progress disposition and report-only recommendation;
- source snapshot and freshness;
- complete versus bounded exploration and exact limits;
- environment and fairness assumptions;
- property coverage and model gaps;
- shortest counterexample timeline mapped to canonical identities;
- disabled-transition reasons and unresolved owner/resource/effect/binding;
- candidate repair and before/after reassessment;
- runtime conformance and supersession history.

Required UI states include checking, finite-model proof, bounded-only, conditional/fairness,
externally gated, intentional wait, recurring service, counterexample found, inconclusive, stale,
and checker failure.

No green or “safe” presentation is legal for bounded, stale, inconclusive, or checker-failure states.

## 11. Architecture alternatives

### Pure workflow/Petri net — rejected as canonical model

Workflow-net soundness contributes option-to-complete, proper-completion and dead-transition
concepts. It is too narrow as the sole Mastermind model for external authority, corrections,
RuntimeBinding, effects, retries, cancellations, priorities, and recurring services.

### Pure graph linting — rejected

Static topology catches missing edges and cycles but cannot establish reachable concurrent behavior,
non-progress lassos, fairness-sensitive starvation, or effect-state safety.

### Direct TLA+/SPIN/Alloy specification as product contract — rejected for V1

These are valuable independent verification backends. Making one the primary product wire would
detach the model from canonical Mastermind identities, add tool/runtime dependencies, and still
require a source compiler and explanation layer.

### Simulation/property testing only — rejected as proof

It is essential for hostile cases and calibration but can only show explored behavior.

### Model-generated review — rejected for authority

Models may help author candidate declarations and explanations. Deterministic validation and checking
own all assurance verdicts.

### Hybrid closed transition model + explicit checking + optional independent formal exports — accepted

This is the smallest architecture that composes Mastermind-specific owners, produces actionable
counterexamples, exposes proof limits, and remains implementation-independent.

## 12. Decidability and abstraction limits

Classical workflow-net soundness is decidable for the classical bounded formalism, while many
extensions involving richer cancellation or priority semantics make soundness undecidable. Mastermind
therefore does not accept arbitrary executable workflow code as a proof model.

Unbounded worker creation, unbounded queues/data, opaque provider behavior, free-form human behavior,
arbitrary clocks, model-generated transitions, and unknown source joins must be finitized through a
reviewed abstraction or reported as `INCONCLUSIVE_MODEL_GAP`.

A finite model may still be too large to exhaust. State/depth/time/memory limits are published in the
report, and state-space exhaustion weakens the verdict without exception.

V1 does not claim compositional assume-guarantee proof across independently checked submodels.
Submodels may be inlined into one finite root model. True compositional proof is a later capability
requiring explicit interface assumptions/guarantees and an independent soundness review.

## 13. Relationship to adjacent programs

### Executive Attention Frontier

Attention Economics asks which valid executive demand deserves cognition and when. Operation
Assurance asks whether one operation's declared progress system has a reachable black hole.

Operation Assurance may later emit exact `serviceability_reasons` and counterexample references for
EAF to consume. It never ranks demand, computes urgency, suppresses attention, allocates cognition,
wakes a target, or transfers authority.

### Sol watcher hardening / PR #268

Watcher hardening addresses one concrete session-local self-deadlock and account-hardening family.
It remains a hostile regression source. Operation Assurance must not edit or replace its watcher
contract, audit script, runbook, or skill.

### Executive Steward / PR #228

The corrected Steward is the planned production read seam for cross-owner compilation. Until its
identity-grouping correctness blocker is closed and protected, the assurance core remains pure and
fixture-driven. It must not build a parallel federated reader.

## 14. Implementation sequence

1. **OLS-F0 — architecture/source law:** protect this law, detailed design, capability ledger and
   implementation plan with a source-contract test. Records only.
2. **OLS-A1 — pure finite assurance core:** closed model/parser, deterministic explicit checker,
   report wire, CLI and hostile fixtures. No runtime reads/writes.
3. **OLS-A1R — independent adversarial review:** mutation tests for verdict inflation, lasso
   minimization, fairness, null/unknown, stale source and effect-unknown escape.
4. **OLS-A2 — canonical source compiler:** after corrected Steward protection, compile one existing
   operation/plan snapshot without new persistence.
5. **OLS-A3 — Steward/Control Room projection:** explain reports and counterexamples through existing
   read/product owners.
6. **OLS-A4 — historical and synthetic calibration:** measure false positives/negatives, model gaps,
   coverage and checker cost against frozen incidents and valid waits.
7. **OLS-A5 — report-only admission/expansion integration:** attach the assessment before selected
   operation expansion; no hard gate.
8. **OLS-A6 — runtime conformance:** compare actual accepted events to the model through existing
   event/Wake paths and invalidate stale assessments.
9. **OLS-C1 — real operational canary:** find a real defect, repair the operation contract, rerun the
   actual path, and prove changed operational outcome without Chairman rescue.
10. **OLS-G1 — enforcement promotion ruling:** only calibrated deterministic defect classes may be
    proposed for stronger gating under separate authority.

## 15. Completion ruler

The program is complete only when:

- canonical source compilation is correction-safe and owner-attributed;
- finite-model, bounded and inconclusive results are never conflated;
- hostile historical incidents are caught with actionable minimal witnesses;
- valid waits, capacity parking, external gates and recurring services avoid unacceptable false
  positives;
- Steward/Control Room explains the result;
- one real report-only canary changes an operational outcome;
- runtime/model drift is visible;
- durable Agent OS and GitHub evidence allow a fresh session to recover the result;
- any enforcement promotion receives a separate evidence-backed ruling.

Protecting OLS-F0 makes only the architecture and no-rebuild law true. It does not make the checker,
compiler, product, admission integration, runtime conformance, or canary live.

## 16. Primary research basis

The detailed design records the exact sources. Load-bearing findings include:

- W.M.P. van der Aalst et al., *Soundness of workflow nets: classification, decidability, and
  analysis* — classical workflow-net soundness and the undecidability introduced by many richer
  extensions.
- Leslie Lamport's TLA+/PlusCal fairness material — weak and strong fairness are explicit liveness
  assumptions, not defaults.
- SPIN verifier documentation — shortest safety traces through breadth-first search and
  acceptance/non-progress cycles for liveness.
- Apalache documentation — fixed finite data and bounded-execution limits for bounded symbolic
  checking.
- Alloy 6 documentation — lasso traces, bounded time horizons, and the practical cost of complete
  finite model checking.
