# Mastermind Operation Liveness & Soundness — Architecture Freeze

**Date:** 2026-08-30  
**Owner:** Sol, AI CEO of Mastermind-X  
**Chairman:** Chris  
**Operation:** `mastermind-operation-liveness-soundness-20260830-sol-001`  
**Protected Mastermind source:** `28d365cceaef6efb0a26e0ac9af51ead44695d60`  
**Macro source observed during freeze:** `ede7e065a90b294e9835e98e5326a84e1c14d038`  
**Terminal protected source observed during freeze:** `afbc839e89c9e91d715c67872c44cf49895ee575`  
**Skillpack:** `mastermind.sol_skillpack.v1` v1.0.1 / bootstrap-major 1  
**Capability state:** `SPEC_ONLY / RECORDS_ONLY / PRODUCTION_INERT`

## 1. Executive thesis

Mastermind has accumulated strong local contracts:

- Executive OS owns durable Job/Attempt/Worker/Event state, leases, fences and effects.
- Agent OS preserves durable organizational responsibility, decisions, discoveries and handoffs.
- Agent Dialogue preserves the canonical company carrier.
- Wake preserves attention obligations and delivery/ACK distinctions.
- SessionTarget/RuntimeBinding and the protected Stage-A Sol action-target resolver preserve exact
  target identity without alias election.
- Capacity/Model Router preserve placement and eligibility.
- Operator Continuation preserves bounded Attempt rollover context.
- Effect-unknown law prevents blind retry/failover.
- Parent-continuation law identifies the active-parent/no-successor hole.

Those local contracts do not yet answer a composed question:

> Can a proposed operation, under its declared topology and assumptions, progress without entering a
> reachable state where every local owner is behaving legally but the organization can no longer
> complete, resume, reconcile, or escalate?

The capability must turn that question into a deterministic, explainable, source-attributed
assessment. The moat is not a decorative graph. It is the ability to admit more ambitious autonomous
work because Mastermind can expose cross-seam black holes before the Chairman becomes the recovery
daemon.

## 2. Current-state archaeology and disagreement ledger

### 2.1 Protected implementation facts

At the protected source used for this freeze:

| Surface | Current observed state |
|---|---|
| Executive runtime | durable SQLite lifecycle with atomic Job/Attempt/Worker/Event changes; existing production/runtime proof must remain owner-specific |
| transport-neutral request identity | protected local implementation |
| deterministic child identity | protected local implementation |
| canonical dialogue ensure | protected local implementation, not a new dialogue store |
| persisted Wake carrier | protected but production-disarmed |
| RuntimeBinding projection | protected, read-only and ABA-safe |
| Sol action target Stage A | protected at `28d365c...`, `BUILT_NOT_PROVEN / PRODUCTION_INERT` |
| Operator Continuation contract | protected pure contract; runtime phases separately gated |
| parent-active/no-successor | accepted source law; full production composition not proven |
| whole-operation assurance compiler/checker | `NOT_BUILT` |
| Control Room assurance experience | `NOT_BUILT` |
| report-only admission integration | `NOT_BUILT` |
| real operational canary | `NOT_BUILT` |

### 2.2 Current collisions

- Mastermind PR #228 owns `control_plane/executive_steward.py` and its tests. It is open and has a
  known identity-grouping correctness blocker. Operation Assurance must not fork a parallel
  federated reader.
- Mastermind PR #268 is open/draft at head `4c0cabfd5e66cc79e17fc06c542839b0cbd53e82`.
  It owns watcher hardening paths and is a regression source, not this program's implementation
  carrier.
- Mastermind PR #275 is the Executive Attention Frontier architecture. It owns prioritization of
  valid cognition demand, not operation liveness.
- Mastermind PR #266 owns the current cognition-route guard/Model Router path.
- Open Macro PR #6604 touches `config/mastermind_programs.yml`; semantic-registry edits for this
  program must avoid a blind concurrent write.

### 2.3 Corrected projection

The commission recorded a Slack projection that PR #268 was protected. Action-time GitHub truth is
open/draft. The architecture preserves that disagreement as evidence and follows GitHub for
implementation truth.

### 2.4 Agent OS registration gap

Macro Agent OS requires every workstream to reference a valid program key. Current Macro still
contains `DSC:EXECUTIVE-OS-NO-PROGRAM-ROW`: no `executive-os` program exists in
`config/mastermind_programs.yml`. A new OLS workstream must not be attached to an approximate parent.

The lawful durable sequence is:

1. protect OLS source law in Mastermind;
2. coordinate a records-only semantic-registry repair under the existing semantic-system-map owner
   after current `config/mastermind_programs.yml` collisions clear;
3. add `WS:OPERATION-LIVENESS-SOUNDNESS` only against that valid program key;
4. use standalone Agent OS decisions/discoveries only when their schema and `affects` references are
   truthful in the interim.

## 3. Research synthesis

### 3.1 Workflow-net soundness

Classical workflow nets provide three essential ideas:

1. every reachable execution state retains an option to complete;
2. proper completion leaves only the intended terminal token and no residue;
3. no declared task is dead.

The literature also establishes an important boundary: classical soundness notions are decidable for
workflow nets, while many extensions involving cancellation, reset behavior or priorities make those
notions undecidable. Mastermind includes cancellation, retry, external gates, priorities, identities,
unbounded future work, and correction. A direct claim of classical workflow-net soundness would
therefore be false unless the operation is deliberately abstracted into a finite restricted model.

### 3.2 Temporal model checking

TLA+/PlusCal makes the safety/liveness split explicit and treats weak and strong fairness as
assumptions. SPIN finds shortest safety traces through breadth-first search and detects
acceptance/non-progress cycles for liveness. These are directly useful for Mastermind's progress
obligations and lasso counterexamples.

Apalache and Alloy reinforce the scope law:

- finite state/data domains are load-bearing;
- bounded checking reasons only within a published horizon;
- complete finite checking may still exhaust practical time or memory;
- liveness witnesses naturally have lasso form: a finite prefix and repeating cycle.

### 3.3 Commercial workflow systems

Mainstream workflow platforms generally provide syntax/schema validation, local state testing,
retry behavior and durable execution. Those capabilities are useful but do not compose
organizational responsibility, exact action target, Wake/ACK, external-effect uncertainty, parent
continuation, capacity and durable handoff across Mastermind's owner graph.

Mastermind's differentiator is the organizational composition, not merely validating a DAG file.

## 4. Rejected architectures

### 4.1 One giant Petri net

A Petri projection is excellent for tokens, concurrency, joins and residue. Encoding every
RuntimeBinding generation, external effect, correction, external authority and recurring service as
Petri-net machinery would produce a misleading or intractable model and obscure source ownership.

**Ruling:** optional diagnostic/export backend, not canonical V1 model.

### 4.2 Generic graph linter

A dependency graph can find missing targets and simple cycles. It cannot determine whether a cycle is
reachable, whether an exit is enabled, whether retry is unsafe because an effect is unknown, or
whether starvation violates a declared fairness contract.

**Ruling:** use graph lint as a cheap pre-pass, never as the full assurance claim.

### 4.3 TLA+/SPIN/Alloy source as the product wire

A general formal specification is powerful but still needs a source compiler, Mastermind identity
mapping, correction law, explanation contract and product projection. It would also add an external
toolchain before the domain model is stable.

**Ruling:** independent export/audit after V1, not the first runtime dependency.

### 4.4 Simulation only

Fault schedules and property-based generation are essential for calibration and opaque integrations.
They cannot prove absence of a trace they did not explore.

**Ruling:** evidence and calibration, not proof authority.

### 4.5 LLM workflow judge

A model can spot plausible holes and explain formal output. It cannot deterministically enumerate the
state space, guarantee minimal traces or hold admission authority.

**Ruling:** explanation/authoring assistant only.

### 4.6 New liveness runtime or supervisor

A service that owns its own operation states, queue, retries, watchers or remediation would duplicate
Executive OS and Wake.

**Ruling:** rejected by design.

## 5. Accepted architecture

### 5.1 Four layers

```text
existing canonical owners
        |
        v
source-attributed immutable snapshot/compiler
        |
        v
closed finite Operation Assurance Model
        |
        +--> deterministic static checks
        +--> explicit-state reachable graph
        +--> SCC/lasso/fairness analysis
        +--> optional later independent formal exports
        |
        v
source-attributed assurance report + minimal repair witness
        |
        +--> CLI / tests
        +--> corrected Steward / Control Room
        +--> report-only admission/expansion evidence
        +--> runtime conformance
```

### 5.2 Why explicit-state Python first

The first executable core should use the Python standard library and be pure:

- it integrates naturally with current Python contracts;
- every state and transition can retain exact canonical IDs and source refs;
- deterministic BFS gives minimal safety prefixes;
- SCC algorithms give transparent non-progress components;
- the implementation is hermetic and mutation-testable;
- no Java, Go, solver, JVM, native binary or external service becomes an admission dependency;
- an independent TLA+/SPIN/Alloy export remains possible after the model stabilizes.

A symbolic backend is admitted later only after measured state explosion demonstrates need and the
backend preserves identical verdict and evidence semantics.

## 6. Model wire

### 6.1 Top-level schema

Conceptual closed wire:

```json
{
  "schema": "mastermind.operation_assurance_model.v1",
  "model_id": "oam_...",
  "operation_ref": {"operation_key": "...", "root_job_id": null},
  "compiler": {"name": "...", "version": "..."},
  "source_snapshot": {"schema": "...", "sources": [], "snapshot_hash": "..."},
  "state_domains": {},
  "initial_state": {},
  "transitions": [],
  "terminal_outcomes": [],
  "recurring_progress_outcomes": [],
  "obligations": [],
  "resources": [],
  "external_gates": [],
  "fairness_assumptions": [],
  "environment_assumptions": [],
  "safety_properties": [],
  "property_set": "mastermind.operation_assurance.properties.v1",
  "exploration_limits": {},
  "known_model_gaps": []
}
```

The exact implementation schema is allowed to refine field names before OLS-A1 review, but may not
weaken the semantic requirements below.

### 6.2 State

A state is a canonical finite map of declared variables to values from closed finite domains.
Examples:

```text
job.<id>.status
attempt.<id>.status
worker.<id>.status
binding.<responsibility>.generation
turn.<child>.owner
carrier.<operation>.identity
effect.<operation>.state
obligation.<id>.state
gate.<id>.state
resource.<id>.holder
parent.<id>.continuation
clock.<deadline>.phase
service.<id>.progress_epoch
```

The model does not use arbitrary wall-clock arithmetic. Source-owned time is finitized into explicit
phases such as `BEFORE_REVIEW`, `REVIEW_DUE`, `OVERDUE`, or another reviewed closed domain.

### 6.3 Transitions

Every transition contains:

```text
transition_id
kind
actor_class
authority_requirement
guards
effects
progress_tags
source_refs
fairness_ref, optional
external_assumption_ref, optional
```

Guards and effects use a closed declarative grammar. V1 allows equality/membership, obligation
presence/state, resource holder, exact identity/binding generation, effect state, gate state and
finite clock phase. No arbitrary executable expression is accepted.

Nondeterminism is represented by multiple explicitly named transitions. Ingestion order never
changes semantic ordering; the checker sorts by stable identity.

### 6.4 Obligations

An obligation is the durable analytical representation of something that must be discharged:

```text
ACTION
RETURN
PARENT_CONTINUATION
EFFECT_RECONCILIATION
CAPACITY_RELEASE
RESOURCE_RELEASE
WAKE_CONSUMPTION
HANDOFF_CONSUMPTION
TERMINAL_CLEANUP
RECURRING_PROGRESS
```

It points to the existing canonical identity that owns the real fact. The model itself cannot create
or satisfy a real obligation.

### 6.5 Resources

Resources cover finite exclusive or bounded assets relevant to progress:

- Worker/Attempt ownership;
- quota class/placement slot;
- action-authoritative turn;
- carrier writer;
- external-effect right;
- review slot;
- parent continuation slot.

A resource in the model is a projection, not an allocator or lock.

### 6.6 Gates and waits

A gate/wait records:

```text
gate_id
disposition = EXTERNAL_GATE | INTENTIONAL_WAIT
authority_or_owner
release_condition
observation_or_return_source
wake_or_review_path
time_contract
correction_contract
escalation_or_close_path
source_refs
```

Missing any required field makes the state a model gap or progress defect, not a valid wait.

### 6.7 Source snapshot

Each source item includes:

```text
owner
source_kind
source_identity
schema_version
content_or_event_digest
effective_at, nullable only when owner has no such concept
observed_at, nullable only when owner has no such concept
correction_generation_or_supersession_ref
freshness_state
conflict_state
```

Snapshot and model hashes use canonical UTF-8 JSON with sorted keys and no NaN/Infinity.

## 7. Analysis semantics

### 7.1 Structural validation

Before exploration:

- exact top-level and nested grammar;
- finite non-empty state domains;
- canonical identities and references;
- one valid initial state;
- transition guards/effects within domains;
- all property/assumption references resolved;
- no duplicate transition/obligation/resource/gate/fairness/property identities;
- at least one accepted terminal, recurring or gated disposition unless the model explicitly claims
  an intentionally impossible/refusal operation;
- no executable code or forbidden opaque guard.

Malformed models are refused; they do not yield an assurance verdict.

### 7.2 Reachability

Use deterministic BFS from the initial state.

Receipt:

```text
states_discovered
transitions_considered
max_depth_reached
complete_state_space
limit_reason
duration_ms
peak_frontier
```

`complete_state_space=true` only when the queue drains without any configured state/depth/time/memory
limit or unsupported transition.

### 7.3 Safety checks

Safety violations are checked while exploring. The first counterexample is shortest by BFS.
Tie-breaking is lexicographic over canonical transition IDs and then state fingerprints.

Core V1 safety predicates:

- `ONE_OPERATION_ONE_CARRIER`
- `ONE_ACTION_AUTHORITY`
- `CURRENT_BINDING_REQUIRED`
- `NO_STALE_ATTEMPT_AUTHORITY`
- `NO_EFFECT_UNKNOWN_ESCAPE`
- `TYPED_RETRY_ONLY`
- `NO_TERMINAL_RESIDUE`
- `NO_SOURCE_CONFLICT_PASS`

### 7.4 Option-to-complete

After graph construction, reverse-reachability from all accepted good outcomes identifies states with
an option to complete.

A reachable nonterminal state not covered by a valid gate/wait/recurring outcome and absent from the
reverse-reachable set violates `OPTION_TO_COMPLETE`.

This is existential completion from each reachable state, not proof that every scheduler run will
terminate.

### 7.5 Proper completion

For every accepted terminal state:

- all non-persistent obligations discharged;
- no active child;
- no active lease/resource;
- no unresolved effect;
- no open required carrier turn;
- parent terminal or continuation consumed;
- no current modifying authority remains.

Adverse terminal outcomes may preserve immutable historical evidence; that is not residue.

### 7.6 Non-progress cycles

Run Tarjan or Kosaraju SCC analysis over reachable states.

Classify:

- `CLOSED_NON_PROGRESS_SCC`: no accepted progress/terminal/gate/recurring outcome and no outgoing edge;
- `FAIRNESS_DEPENDENT_CYCLE`: cycle can avoid progress but has an enabled progress exit whose eventual
  service depends on declared fairness;
- `RECURRING_SERVICE_CYCLE`: cycle discharges the required recurring obligation and is valid;
- `BENIGN_TRANSIENT_CYCLE`: cycle cannot remain closed or does not preserve an unresolved obligation.

A liveness witness is prefix + cycle, not an arbitrary long log.

### 7.7 Weak fairness

For a candidate lasso, a weak-fair transition cannot remain enabled at every cycle state without
occurring in the cycle.

The V1 checker may refute a lasso that violates that rule. It must not infer fairness for a transition
without a declared, source-backed fairness reference.

Strong fairness requires detecting transitions enabled infinitely often but not continuously. It is
out of the minimum OLS-A1 scope.

### 7.8 Starvation

For each persistent obligation, search violating lassos where:

- the obligation remains pending through the cycle;
- no cycle step discharges it;
- the lasso satisfies the declared fairness assumptions;
- the operation is not a valid external gate/wait/recurring service for that obligation.

Return the shortest deterministic witness found under the checker ordering.

### 7.9 Dead transitions

A transition marked `required_reachable=true` that is never enabled in the complete reachable graph is
a defect. In bounded/incomplete exploration it remains `UNKNOWN`, never dead by proof.

## 8. Report wire

Conceptual `mastermind.operation_assurance_report.v1`:

```text
schema
report_id
model_id
model_hash
source_snapshot_hash
checker_version
property_set_version
assurance_verdict
progress_disposition
admission_mode
admission_recommendation
property_results
counterexamples
coverage
assumptions
known_model_gaps
freshness
supersedes_report_id
generated_at
report_hash
```

### 8.1 Verdict algorithm

1. source stale/conflicting after compilation -> `MODEL_STALE_OR_INVALID`;
2. load-bearing model gap or unsupported semantics -> `INCONCLUSIVE_MODEL_GAP`;
3. reachable violation -> `UNSAFE_COUNTEREXAMPLE`;
4. complete finite exploration with all required properties satisfied ->
   `PROVEN_WITHIN_FINITE_MODEL`;
5. otherwise -> `BOUNDED_NO_COUNTEREXAMPLE`.

Progress disposition is then computed from accepted outcomes/assumptions and never upgrades the
assurance verdict.

### 8.2 Recommendation algorithm

V1 recommendation is advisory and deterministic:

- unsafe -> `REPORT_ONLY_REPAIR`;
- stale/conflicted -> `REPORT_ONLY_RECONCILE`;
- valid named external gate -> `REPORT_ONLY_AWAIT_GATE`;
- finite proof or bounded result with no load-bearing gap -> `REPORT_ONLY_PROCEED`, while the UI still
  distinguishes proof from bounded evidence;
- inconclusive -> `REPORT_ONLY_NO_RECOMMENDATION`.

This algorithm must not become a hard admission gate in OLS-A1.

## 9. Counterexample minimization

### 9.1 Safety

BFS parent links reconstruct the shortest prefix to the first violating state under deterministic
ordering.

### 9.2 Liveness

For each violating SCC:

1. BFS from initial state to each candidate entry;
2. choose shortest prefix, then canonical entry fingerprint;
3. within the SCC, find the shortest cycle returning to the entry that demonstrates the property;
4. break ties by canonical transition sequence.

### 9.3 Actionability

Each step carries:

```text
before_state_hash
transition_id
actor/authority
source_refs
changed variables
obligations created/discharged
resources acquired/released
disabled expected transitions and reason
after_state_hash
```

Repair candidates are deterministic pattern matches, not autonomous modifications:

- missing owner -> name required owner/binding source;
- missing continuation -> add explicit parent continuation obligation/path;
- effect-unknown escape -> remove retry/failover edge and require reconciliation;
- carrier split -> reconcile canonical carrier;
- terminal residue -> add cleanup/release transition;
- unserviceable action target -> restore exact binding or surface typed target conflict;
- capacity cycle -> release/order resources or classify valid parking;
- weak-fair starvation -> amend scheduler/service contract only through its owner.

## 10. Failure and degradation vocabulary

```text
MODEL_SCHEMA_INVALID
MODEL_DOMAIN_UNBOUNDED
MODEL_REFERENCE_MISSING
MODEL_SOURCE_CONFLICT
MODEL_SOURCE_STALE
MODEL_GUARD_UNSUPPORTED
MODEL_TRANSITION_UNSUPPORTED
STATE_LIMIT_REACHED
DEPTH_LIMIT_REACHED
TIME_LIMIT_REACHED
MEMORY_LIMIT_REACHED
CHECKER_INTERNAL_ERROR
NO_TERMINAL_OR_PROGRESS_OUTCOME
OWNERLESS_OBLIGATION
ACTION_AUTHORITY_CONFLICT
RUNTIME_BINDING_UNAVAILABLE
RUNTIME_BINDING_STALE
DIALOGUE_CARRIER_SPLIT
WAKE_PATH_UNAVAILABLE
PARENT_ACTIVE_NO_SUCCESSOR
EFFECT_UNKNOWN_ESCAPE
UNTYPED_RETRY
RESOURCE_CYCLE
TERMINAL_RESIDUE
CLOSED_NON_PROGRESS_SCC
FAIRNESS_DEPENDENT_CYCLE
STARVATION_WITNESS
EXTERNAL_GATE_INCOMPLETE
INTENTIONAL_WAIT_INCOMPLETE
RUNTIME_MODEL_DRIFT
```

These are assurance findings/reasons, not Executive lifecycle states.

## 11. Product experience

### 11.1 Primary persona

Steward/Control Room operator or Sol reviewing an autonomous operation before expansion.

### 11.2 Primary journey

```text
select operation / proposed plan
-> compile current source snapshot
-> see source coverage and model gaps
-> run assessment
-> inspect exact verdict/progress basis
-> when unsafe, inspect minimal causal trace
-> open canonical owner/evidence links
-> repair the operation contract in its owning system
-> recompile/reassess
-> compare before/after
-> proceed under report-only recommendation
```

### 11.3 Reference composition

Header:

```text
Operation Assurance
UNSAFE_COUNTEREXAMPLE · REPORT_ONLY_REPAIR
Model 8b2... · 100% finite exploration · 1,248 states
```

Body:

- **Why:** `EFFECT_UNKNOWN_ESCAPE`
- **Counterexample:** five-step prefix, no cycle
- **Break:** `ATT-...` loses provider response; transition `retry-on-alternate-realm` remains enabled
- **Forbidden consequence:** second modifying carrier can launch before reconciliation
- **Repair:** disable retry edge until existing effect owner emits reconciled terminal fact
- **Sources:** exact Job/Attempt/Event/RuntimeBinding/law refs
- **Assumptions and gaps:** visible, never hidden in a tooltip.

For a valid gate:

```text
INCONCLUSIVE_MODEL_GAP · EXTERNALLY_GATED · REPORT_ONLY_AWAIT_GATE
Gate: Chairman credential confirmation
Return path: exact operation carrier
No autonomous completion claim
```

### 11.4 Required failure states

- source read unavailable;
- source conflict;
- model compile failure;
- checker refused;
- bounded state explosion;
- stale report;
- no counterexample but incomplete coverage;
- valid wait;
- external gate;
- recurring service;
- runtime drift.

## 12. Integration sequencing

### OLS-F0 — this architecture carrier

Files:

- `docs/OPERATION_LIVENESS_SOUNDNESS_LAW.md`
- `docs/superpowers/specs/2026-08-30-operation-liveness-soundness-design.md`
- `research/MASTERMIND_OPERATION_LIVENESS_SOUNDNESS_CAPABILITY_LEDGER_2026-08-30.md`
- `docs/superpowers/plans/2026-08-30-operation-assurance-core.md`
- `tests/test_operation_liveness_soundness_source_contract.py`

Proof:

- source-contract test;
- exact-head repository CI;
- collision recheck;
- independent adversarial architecture review;
- expected-head merge only.

### OLS-A1 — pure assurance core

Expected new paths:

```text
control_plane/operation_assurance_model.py
control_plane/operation_assurance_checker.py
control_plane/operation_assurance_report.py
scripts/operation_assurance.py
tests/test_operation_assurance_model.py
tests/test_operation_assurance_checker.py
tests/test_operation_assurance_cli.py
tests/fixtures/operation_assurance/*.json
```

No edits to Executive Runtime, Steward, Wake, watcher, Model Router, SessionTarget, RuntimeBinding,
Agent OS or Control Room.

Acceptance:

- closed JSON parser rejects unknown/opaque/unbounded input;
- deterministic full finite exploration;
- shortest safety counterexamples;
- deterministic lasso for closed non-progress SCC;
- no-effect-unknown escape;
- valid wait/gate/recurring distinction;
- bounded result cannot say proved;
- checker error cannot say pass;
- repeated run byte-identical except an explicitly isolated generated timestamp;
- CLI is report-only and performs no network/store/runtime mutation.

### OLS-A2 — source compiler

Gate: corrected Executive Steward #228 protected.

Compile one real existing operation from accepted immutable read facts. No direct multi-store
side-read and no new cache/database.

### OLS-A3 — product projection

Extend the accepted Steward/Control Room read surfaces. The assurance engine remains pure and the UI
stores no independent result truth.

### OLS-A4 — calibration

Frozen corpus:

- Sol watcher self-deadlock;
- dialogue carrier split;
- parent terminal/parent active/no successor;
- delivered but unacknowledged target;
- stale or missing RuntimeBinding;
- effect-unknown alternate route;
- capacity unavailable valid parking;
- natural-evidence/calendar wait;
- circular dependencies;
- weak-fair starvation;
- stale Slack “done” versus canonical GitHub disagreement;
- recurring service;
- cancellation and lawful adverse terminal outcome.

Measure:

```text
incident detection recall
valid-wait false positive rate
counterexample minimality
model/source coverage
inconclusive rate
state count / transition count / runtime
repair acceptance rate
```

No enforcement promotion from one corpus.

### OLS-A5 — report-only admission/expansion

Attach the current assessment to selected CEO/COO plan expansion without blocking. If the assessment
is stale, missing or inconclusive, show it honestly. Do not convert availability of the checker into a
mandatory hard gate.

### OLS-A6 — runtime conformance

Consume existing accepted events and source snapshots. Detect unmodeled transitions, invalidated
assumptions and stale source. Route attention through existing Wake only.

### OLS-C1 — canary

A low-risk real operation must:

1. compile with a genuine counterexample;
2. be repaired in the actual owner contract;
3. recompile to a stronger truthful result;
4. execute through the real path;
5. reach its intended consumer without Chairman rescue;
6. preserve zero duplicate lifecycle/queue/session/retry owners.

### OLS-G1 — promotion

Only after prospective evidence may Sol propose a separate promotion law for narrow deterministic
classes such as malformed model, effect-unknown retry escape, or ownerless modifying transition.
Chairman/new authority is required for any material hard gate.

## 13. Capability ledger at freeze

| Capability | State | Evidence / limit |
|---|---|---|
| Executive lifecycle and event owner | `PROVEN_LIVE` at owner level | existing runtime and production program; this PR does not re-prove every deployment |
| Agent OS durable organizational records | `PROVEN_LIVE` | current file-per-record store and generated CEO views |
| transport-neutral root identity | `BUILT_NOT_PROVEN` for autonomous cutover | protected implementation; broader cutover pending |
| deterministic child identity | `BUILT_NOT_PROVEN` | protected local seam |
| canonical dialogue ensure | `BUILT_NOT_PROVEN` | protected, production-disarmed |
| persisted Wake carrier | `BUILT_NOT_PROVEN` | protected, production-disarmed |
| RuntimeBinding projection | `BUILT_NOT_PROVEN` | protected read-only seam |
| exact Sol action target Stage A | `BUILT_NOT_PROVEN` | protected at `28d365c...`, production-inert |
| parent-continuation detection | `PARTIAL` | accepted source law; complete product/runtime composition not proven |
| watcher self-deadlock hardening | `BUILT_NOT_PROVEN` | PR #268 open/draft |
| Executive Steward normalized read | `BUILT_NOT_PROVEN / BROKEN` | PR #228 open with correctness blocker |
| Executive Attention Frontier | `SPEC_ONLY` | PR #275 open |
| whole-operation assurance model/checker | `NOT_BUILT` | no matching code or PR found |
| canonical source compiler | `NOT_BUILT` | depends on corrected Steward |
| Control Room assurance card | `NOT_BUILT` | later wave |
| report-only admission integration | `NOT_BUILT` | later wave |
| runtime conformance | `NOT_BUILT` | later wave |
| real canary | `NOT_BUILT` | completion requirement |

## 14. Formal-method limitations that remain visible

- A finite abstraction can omit a real transition; runtime conformance and source coverage are
  therefore part of product truth.
- Human/Chairman behavior cannot be proved unless represented as an explicit environment assumption.
- Provider internals remain opaque unless their owner supplies a contract.
- Weak fairness does not imply strong fairness.
- A proof in the model does not prove infrastructure availability or faithful implementation.
- Complete finite exploration can still be operationally expensive.
- Compositional proof is not accepted until assume/guarantee interfaces are formalized.
- An actionable counterexample refutes the model/property but does not automatically identify the
  only correct organizational repair.

## 15. Primary-source bibliography

1. W.M.P. van der Aalst, K.M. van Hee, A.H.M. ter Hofstede, N. Sidorova,
   H.M.W. Verbeek, M. Voorhoeve, and M.T. Wynn, “Soundness of workflow nets:
   classification, decidability, and analysis,” *Formal Aspects of Computing* 23(3), 2011.
   https://research.tue.nl/en/publications/soundness-of-workflow-nets-classification-decidability-and-analys/
2. H.M.W. Verbeek and M.T. Wynn, “Verification,” workflow-net soundness summary.
   https://research.tue.nl/en/publications/verification/
3. Leslie Lamport, PlusCal Tutorial Session 9, weak and strong fairness.
   https://lamport.azurewebsites.net/tla/tutorial/session9.html
4. Gerard J. Holzmann, SPIN Verifier's Roadmap, shortest safety trails and liveness cycles.
   https://spinroot.com/spin/Man/4_SpinVerification.html
5. Apalache documentation, finite parameters/data and bounded executions.
   https://apalache-mc.org/docs/apalache/index.html
6. Alloy 6 documentation, lasso traces and bounded/complete finite model checking.
   https://alloytools.org/alloy6.html
7. AWS Step Functions `ValidateStateMachineDefinition`, representative commercial static workflow
   diagnostics.
   https://docs.aws.amazon.com/step-functions/latest/apireference/API_ValidateStateMachineDefinition.html
