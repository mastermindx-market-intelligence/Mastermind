# Operation Assurance Core Implementation Plan

**Operation:** `mastermind-operation-liveness-soundness-20260830-sol-001`  
**Wave:** `OLS-A1`  
**Owner:** bounded implementation worker under Sol acceptance  
**Current protected pickup after F0:** exact protected descendant selected at commission time  
**Capability target:** pure deterministic model parser, checker, immutable report, CLI, and hostile fixtures

## CONTROLLING OLS-A1 IMPLEMENTATION NOTICE

Some earlier task examples are historical drafting residue. A worker must **do not implement** any
example that conflicts with the following sources. Read them in this exact precedence order before
writing the first test:

1. `docs/superpowers/specs/2026-08-30-operation-assurance-immutable-report-projection-clarification.md`
2. `docs/superpowers/specs/2026-08-30-operation-assurance-model-fidelity-counterexample-validation-amendment.md`
3. `docs/superpowers/specs/2026-08-30-operation-assurance-a1-trusted-input-total-proof-clarification.md`
4. `docs/superpowers/specs/2026-08-30-operation-assurance-a1-controlling-execution-overlay.md`

Also read the current owner boundaries:

- `docs/superpowers/specs/2026-08-31-operation-liveness-soundness-executive-steward-reconciliation.md`
- `docs/superpowers/specs/2026-08-31-operation-liveness-soundness-sol-capability-fabric-reconciliation.md`
- `docs/superpowers/specs/2026-08-30-operation-liveness-soundness-runtime-observability-reconciliation.md`

This plan is the executable navigation layer. The subject-specific sources above win where they are
more precise.

## 1. Observable mission

Given one authored closed `mastermind.operation_assurance_model.v1` JSON document, the CLI validates
it exactly, deterministically checks the complete reachable finite model within declared bounds, and
emits one canonical immutable `mastermind.operation_assurance_report.v1` with minimal
source-attributed safety or liveness counterexamples and no runtime side effect.

## 2. Why this wave matters

This is the first independently useful Operation Assurance capability. It converts the architecture
from records into a real machine consumer while preserving the no-rebuild boundary. It enables hostile
fixtures and deterministic review before any live-source compiler or Control Room integration is
attempted.

## 3. Route and scope

**Preferred avenue:** `CTO Sol` for reasoning-heavy bounded implementation.  
**Receiver binding:** `CAPACITY_SELECTABLE`.  
**Why:** finite-state semantics, canonical identity, fairness, and counterexample minimization require
strong engineering reasoning, but the architecture is frozen and repository scope is bounded.  
**Why not Fable:** no unresolved cross-repository or principal-level product ambiguity remains in A1.

The concrete worker receives no merge, release, production, Executive, provider, or organizational
authority merely from the route label.

## 4. Exact repository and file map

Repository: `mastermindx-market-intelligence/Mastermind`

Create only:

| Path | Responsibility |
|---|---|
| `control_plane/operation_assurance_model.py` | closed model types, exact parser, validation, canonicalization, model identity |
| `control_plane/operation_assurance_report.py` | exact immutable report wire, identity, validation, serialization |
| `control_plane/operation_assurance_checker.py` | reachability, properties, SCC/fairness products, witnesses, verdict composition |
| `scripts/operation_assurance.py` | bounded report-only JSON CLI |
| `tests/test_operation_assurance_model.py` | grammar, validation, canonical identity, hostile parsing |
| `tests/test_operation_assurance_report.py` | report field set, orthogonal axes, immutable identity |
| `tests/test_operation_assurance_checker.py` | safety, workflow, liveness, fairness, bounds, witnesses |
| `tests/test_operation_assurance_cli.py` | real machine-consumer contract and error boundaries |
| `tests/fixtures/operation_assurance/*.json` | valid, unsafe, bounded, gated, recurring, and hostile models |

No edits to Executive Runtime, Executive Steward, Wake, SessionTarget, RuntimeBinding, Model Router,
Agent OS, Control Room, Runtime Observability, Sol Capability Fabric, Project Workroom, Worker Browser,
GitHub action code, or production deployment paths are permitted in OLS-A1.

## 5. Explicit non-goals

OLS-A1 does not:

- gather or compile live Executive OS, Agent OS, Wake, RuntimeBinding, Capacity, GitHub, Slack, or
  observability facts;
- create a source compiler, source cache, federated reader, Steward extension, or graph database;
- create or mutate lifecycle, admission, retry, placement, Wake, carrier, worker, session, lease,
  effect, or authority state;
- expose a web UI or Control Room card;
- emit current assurance status;
- claim production applicability;
- perform runtime replay;
- support strong fairness;
- block or admit an operation;
- execute any repair candidate.

OLS-A1 stops at a pure report-only CLI.

## 6. Technology and purity boundary

- Python 3.11+
- standard library only in production modules
- pytest for tests
- immutable frozen dataclasses or equivalent immutable value objects
- canonical UTF-8 JSON using sorted keys, compact separators, `ensure_ascii=False`, and
  `allow_nan=False`
- no randomness in production
- no network, socket, subprocess, telemetry, SQLite, filesystem write, dynamic import, plugin, model,
  provider, GitHub, Slack, browser, or source-owner I/O in model/report/checker modules
- CLI may read exactly one explicit file or stdin and write one report to stdout

A valid unsafe model still produces a report and normal CLI process completion. Invalid JSON or a
refused model uses a bounded invalid-input exit. An internal checker failure uses a distinct bounded
checker-refusal exit unless a complete validated report was already finalized.

## 7. Exact model wire

Schema:

```text
mastermind.operation_assurance_model.v1
```

Top-level fields, exact and complete:

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

Property set:

```text
mastermind.operation_assurance.properties.v1
```

### 7.1 Operation reference

```text
operation_key
root_job_id|null
pre_admission_identity|null
```

Exactly one of `root_job_id` and `pre_admission_identity` is non-null. This identity is descriptive
analysis scope, not runtime authority.

### 7.2 Compiler descriptor

```text
name
version
invocation_mode
```

For A1, `invocation_mode` is always `AUTHORED_INPUT`. Caller values cannot switch the checker into a
trusted compiler or replay mode.

### 7.3 Source snapshot

```text
schema
sources[]
snapshot_hash
```

Each source contains:

```text
owner
source_kind
source_identity
schema_version
digest
effective_at|null
observed_at|null
correction_ref|null
freshness
conflict
coverage
truncated
continuation|null
```

Positive authored labels never grant current attestation. Negative `STALE`, `CONFLICTED`,
`INCOMPLETE`, or `UNKNOWN` information may weaken generation-time applicability.

### 7.4 Abstraction contract

```text
kind
concrete_scope
preserves[]
introduced_behavior
excluded_behavior
validation_kind
validation_refs[]
notes[]
```

Closed kinds:

```text
DECLARED_EXACT
SOUND_OVERAPPROXIMATION
TRACE_BACKED_UNDERAPPROXIMATION
HEURISTIC_ABSTRACTION
UNKNOWN_FIDELITY
```

Closed preservation claims:

```text
SAFETY
REACHABLE_COUNTEREXAMPLE
OPTION_TO_COMPLETE
UNIVERSAL_PROGRESS
LIVENESS_UNDER_DECLARED_FAIRNESS
RESOURCE_OWNERSHIP
EFFECT_RETRY_SAFETY
```

Closed validation kinds:

```text
AUTHOR_DECLARATION
SOURCE_COMPILER_ATTESTATION
SOURCE_CONTRACT_REPLAY
RUNTIME_EVENT_REPLAY
INDEPENDENT_FORMAL_EQUIVALENCE
NONE
```

In A1, every positive validation claim is descriptive only.

### 7.5 State domains and state

- each variable ID is a non-empty canonical token;
- each domain is a finite non-empty sequence of unique canonical JSON scalar values;
- booleans are not accepted where integers are required;
- the initial-state key set exactly equals the domain key set;
- every initial value belongs to its declared domain;
- variable order is lexical and stable.

### 7.6 Guards and effects

Guard fields:

```text
variable
op
value
```

Operators:

```text
EQ
NEQ
IN
NOT_IN
```

Effects contain `variable` and `value`. Effects are simultaneous. Duplicate effects for one variable
are parser refusal, not ordered writes.

### 7.7 Transitions

```text
transition_id
kind
actor_class
authority_requirement
guards[]
effects[]
progress_tags[]
source_refs[]
fairness_ref|null
external_assumption_ref|null
required_reachable
```

Transition kinds are a closed set sufficient for progress, modify, reconcile, retry, failover,
release, review, escalate, cancel, refuse, and no-op logical modeling. Logical stuttering is internal
to analysis and is never serialized as an executable operation transition.

Fairness and environment references are bidirectional: the transition and corresponding assumption
must name each other exactly.

### 7.8 Outcomes

```text
outcome_id
kind
guards[]
owned_persistent_obligation_ids[]
owned_persistent_resource_ids[]
source_refs[]
```

Kinds:

```text
TERMINAL_SUCCESS
TERMINAL_REFUSAL
TERMINAL_CANCELLED
TERMINAL_FAILED_SAFE
RECURRING_PROGRESS
```

Terminal outcomes cannot own non-persistent pending obligations or held resources.

### 7.9 Obligations

```text
obligation_id
kind
state_variable
pending_values[]
discharged_values[]
persistent
owner_or_authority
source_refs[]
```

### 7.10 Resources

```text
resource_id
holder_variable
released_values[]
persistent
owner_or_authority
source_refs[]
```

### 7.11 Gates and waits

```text
gate_id
disposition
state_guards[]
owner_or_authority
release_condition
release_transition_ids[]
return_or_observation_source
wake_or_review_path
time_contract
correction_contract
escalation_or_close_path
source_refs[]
```

`release_transition_ids` is non-empty. `escalation_or_close_path` names one listed transition. A
release transition must be enabled in the gate state and reach either a continuing state or named
terminal outcome. Transitionless terminal-boundary prose is refused.

### 7.12 Fairness assumptions

`NONE` is absence of an assumption. A1 accepts only:

```text
kind = WEAK
```

Each assumption has `fairness_id`, `transition_ids`, and `source_refs`. Strong fairness is outside
OLS-A1.

### 7.13 Environment assumptions

```text
assumption_id
kind
transition_ids[]
required_for_property_ids[]
source_refs[]
```

A human or external event assumption does not become scheduler fairness or a promise that the event
will occur.

### 7.14 Safety properties

Exactly one of:

```text
STATE_FORBIDDEN: property_id, kind, violation_when, source_refs
TRANSITION_FORBIDDEN: property_id, kind, when, forbidden_transition_kinds, source_refs
```

Mixed shapes or unknown fields are refused.

### 7.15 Model gaps

```text
gap_id
reason
load_bearing
affects_property_ids[]
affects_transition_ids[]
affects_variable_ids[]
source_refs[]
```

Every reference resolves. Empty affected sets are legal only for a non-load-bearing gap whose reason
states why no checked property can change.

### 7.16 Exploration limits

```text
max_states
max_depth
```

Both are exact integers, not booleans. `max_states >= 1`; `max_depth >= 0`. The state limit also bounds
each augmented property/fairness product. Every exhausted analysis reports its exact reason.

## 8. Exact immutable report wire

Schema:

```text
mastermind.operation_assurance_report.v1
```

Exact fields:

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

Model-analysis verdicts:

```text
UNSAFE_COUNTEREXAMPLE
PROVEN_WITHIN_FINITE_MODEL
BOUNDED_NO_COUNTEREXAMPLE
INCONCLUSIVE_MODEL_GAP
```

Generation-time applicability:

```text
AUTHOR_DECLARED_ONLY
CURRENT_SOURCE_ATTESTED
HISTORICAL_SOURCE_ATTESTED
STALE
CONFLICTED
INCOMPLETE
UNKNOWN
```

A1 cannot produce either trusted attested value from authored input.

Progress dispositions:

```text
AUTONOMOUSLY_LIVE
FAIRNESS_CONDITIONAL
EXTERNALLY_GATED
INTENTIONAL_WAIT
RECURRING_SERVICE
NO_PROGRESS
UNKNOWN
```

A1 recommendations:

```text
REPORT_ONLY_REPAIR
REPORT_ONLY_RECONCILE
REPORT_ONLY_AWAIT_GATE
REPORT_ONLY_NO_RECOMMENDATION
```

`REPORT_ONLY_PROCEED` is rejected in A1.

The report contains no `assurance_verdict`, `current_projection_verdict`, bare
`source_applicability`, current source receipts, current status, current recommendation, recomputation
time, or wall-clock duration.

## 9. Canonical identity

Implement:

```python
canonical_bytes(value) -> bytes
canonical_sha256(value) -> str
state_fingerprint(variable_order, state) -> str
```

Canonical JSON uses sorted keys, separators `(",", ":")`, UTF-8, `ensure_ascii=False`, and
`allow_nan=False`.

`model_hash` is the digest of the canonical normalized model excluding only its derived hash field if
one exists. The report hash is computed from the canonical report body excluding `report_id` and
`report_hash`. Then:

```text
report_id = "oar_" + report_hash[:24]
```

Fixed model plus fixed `generated_at` produces byte-identical report JSON.

## 10. Counterexample wire

Every failed property receives exactly one deterministic minimal witness:

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

Realizability:

```text
DECLARED_MODEL_ONLY
SOURCE_CONTRACT_VALIDATED
RUNTIME_REPLAY_CONFIRMED
POTENTIALLY_SPURIOUS
INVALIDATED
```

A1 emits only `DECLARED_MODEL_ONLY` or `POTENTIALLY_SPURIOUS`, except an invalid negative fixture may
exercise refusal semantics. Authored labels cannot upgrade a witness.

Safety minimization: shortest prefix, then canonical transition sequence, then state fingerprint.
Liveness minimization: shortest prefix + cycle, then canonical transition sequence, then state
fingerprint.

## 11. Mandatory property set

The checker owns and always reports at least:

- `NO_FORBIDDEN_STATE`
- `NO_FORBIDDEN_TRANSITION`
- `NO_EFFECT_UNKNOWN_ESCAPE`
- `ONE_ACTION_AUTHORITY`
- `OPTION_TO_COMPLETE`
- `PROPER_COMPLETION`
- `NO_DEAD_REQUIRED_TRANSITION`
- `NO_POST_TERMINAL_TRANSITION`
- `UNIVERSAL_PROGRESS`
- `RECURRING_PROGRESS_VALID`
- `NO_STARVATION_UNDER_DECLARED_FAIRNESS`
- `FAIRNESS_REALIZABLE`

Authored properties supplement but cannot remove mandatory coverage.

## 12. Verdict composition

1. malformed or unsupported model -> parser refusal, no report;
2. fully materialized definite witness with no relevant invalidating gap ->
   `UNSAFE_COUNTEREXAMPLE` within its fidelity/applicability scope;
3. potentially spurious witness, unknown fidelity, or relevant load-bearing gap ->
   `INCONCLUSIVE_MODEL_GAP` with candidate witness and limitations;
4. all finite domains, complete base graph, every required analysis complete, every mandatory
   property `PASS` or valid `NOT_APPLICABLE`, property-preserving abstraction, and normal termination
   -> `PROVEN_WITHIN_FINITE_MODEL`;
5. declared bound reached with no definite witness -> `BOUNDED_NO_COUNTEREXAMPLE` or
   `INCONCLUSIVE_MODEL_GAP` according to the missing analysis;
6. otherwise -> `INCONCLUSIVE_MODEL_GAP`.

Source applicability is composed separately. Stale or conflict preserves the model result and forces
`REPORT_ONLY_RECONCILE`. A declared-exact model-only unsafe witness yields `REPORT_ONLY_REPAIR`.
A complete gate or wait may yield `REPORT_ONLY_AWAIT_GATE`. Every other A1 result yields
`REPORT_ONLY_NO_RECOMMENDATION`.

## 13. Ordered implementation sequence

### Task 0 — isolated pickup and baseline

- create an isolated worktree/branch from the exact accepted protected F0 descendant;
- collision-check every file in Section 4 and all active PRs;
- run the full repository test gate before changes;
- stop on a dirty or failing baseline not explained by the accepted pickup.

### Task 1 — model grammar and identity

RED first:

- minimal corrected model with required abstraction contract;
- exact-key rejection;
- canonical hash under mapping/list permutations;
- duplicate/non-finite/out-of-domain/ref mismatch refusal;
- authored trust ceiling.

GREEN:

- immutable types;
- exact parser;
- canonical helpers;
- model serialization and identity.

Focused verification:

```bash
pytest -q tests/test_operation_assurance_model.py
```

### Task 2 — immutable report

RED first:

- exact field set from Section 8;
- orthogonal model/applicability/disposition/recommendation axes;
- non-circular identity;
- UTC generated-at validation;
- no current fields or wall-clock duration;
- proof anti-inflation invariants.

GREEN:

- immutable report types;
- report validation;
- finalization and canonical serialization.

Focused verification:

```bash
pytest -q tests/test_operation_assurance_report.py
```

### Task 3 — reachability and transition semantics

RED first:

- lexical transition order;
- simultaneous effects;
- shortest predecessor selection;
- depth/state limit receipts;
- deterministic state fingerprints;
- terminal states retained for absorption checks.

GREEN:

- transition evaluator;
- immutable reachability graph;
- BFS with complete work counts.

### Task 4 — safety and workflow soundness

RED first:

- forbidden state and transition;
- `EFFECT_UNKNOWN` retry/failover escape;
- one-action-authority violation;
- option-to-complete;
- proper terminal residue;
- dead required transition;
- cancellation and refusal terminals;
- `NO_POST_TERMINAL_TRANSITION`.

GREEN:

- deterministic property evaluators;
- reverse completion;
- proper-completion and absorption analysis;
- one minimal witness per failed property.

### Task 5 — liveness, weak fairness, and starvation

RED first:

- non-progress self-loop with outgoing completion edge;
- weak fairness excludes only continuously enabled untaken transition;
- transition disabled in one cycle state does not trigger weak fairness;
- fair violating closed walk that combines two simple cycles;
- vacuous/unrealizable fairness cannot manufacture proof;
- persistent obligation starvation;
- valid recurring progress;
- empty obligation list cannot hide root livelock;
- fairness product state-limit receipt.

GREEN:

- cyclic SCC enumeration;
- augmented seen-or-disabled fairness product;
- recurring-progress and starvation evaluators;
- deterministic shortest lasso construction.

### Task 6 — final verdict composition

RED first:

- base BFS complete but fairness product incomplete cannot prove;
- unknown mandatory property cannot prove;
- relevant gap weakens witness/proof while unrelated non-load-bearing gap does not hide a definite
  witness;
- under-approximate no-witness cannot prove;
- complete definite witness survives unrelated later bound;
- internal exception never returns a healthy default.

GREEN:

- compose model verdict, applicability, disposition, and recommendation separately;
- populate per-analysis coverage and exact incomplete reasons;
- refuse partial unvalidated reports after internal failure.

### Task 7 — CLI and fixtures

Required fixtures:

```text
safe_finite.json
effect_unknown_failover.json
ownerless_modifying_transition.json
carrier_split.json
stranded_parent.json
stale_binding.json
stale_projection.json
chairman_external_gate.json
capacity_valid_wait.json
natural_time_wait.json
recurring_service.json
safe_cancellation.json
weak_fair_progress.json
weak_fair_disabled_cycle.json
combined_cycle_fair_lasso.json
fairness_unrealizable.json
terminal_transition_violation.json
bounded_exploration.json
unknown_fidelity.json
```

CLI behavior:

```text
operation-assurance MODEL.json [--pretty]
operation-assurance - [--pretty]
```

No flag may request trusted source mode, replay mode, admission, mutation, retry, Wake, placement,
GitHub, browser, or runtime action.

Exit contract:

- `0`: valid report, including unsafe/bounded/inconclusive;
- `2`: invalid JSON or refused closed model;
- `3`: internal checker/report refusal;
- any other exit is reserved and not introduced in A1.

Output contains no absolute local path or secret. Errors are one bounded line with no traceback by
default.

### Task 8 — adversarial and no-side-effect fence

Add mutation-killing tests for at least:

1. accepting unknown fields;
2. accepting duplicate JSON object keys at the CLI parse boundary;
3. accepting NaN/Infinity;
4. trusting authored source/compiler/replay labels;
5. omitting abstraction contract;
6. allowing one-sided fairness or environment references;
7. ordering duplicate effects;
8. treating progress tags as recurring evidence;
9. suppressing mandatory properties;
10. limiting liveness to closed SCCs;
11. searching only simple cycles;
12. treating weak fairness as strong fairness;
13. accepting vacuous fairness;
14. proving after incomplete product search;
15. erasing a definite witness after an unrelated bound;
16. permitting post-terminal transitions;
17. accepting descriptive gate prose without modeled release/closure;
18. computing report identity circularly;
19. including duration in canonical output;
20. emitting current status from A1;
21. emitting `REPORT_ONLY_PROCEED` from authored input;
22. performing network, subprocess, telemetry, SQLite, runtime, or source-owner I/O.

Run focused tests, then the complete repository gate.

## 14. Complete machine journey

### Valid safe model

Input parses -> all analyses complete -> immutable report with finite-model verdict,
`AUTHOR_DECLARED_ONLY`, and `REPORT_ONLY_NO_RECOMMENDATION` -> exit 0.

### Definite authored unsafe model

Input parses -> shortest witness materializes -> immutable report with
`UNSAFE_COUNTEREXAMPLE`, `DECLARED_MODEL_ONLY`, and `REPORT_ONLY_REPAIR` -> exit 0.

### Potentially spurious model

Input parses -> candidate witness found under over-approximation/relevant gap -> report keeps witness,
limitations, `POTENTIALLY_SPURIOUS`, and `INCONCLUSIVE_MODEL_GAP` -> exit 0.

### Bounded analysis

Input parses -> declared limit reached before complete no-witness proof -> report names exact incomplete
analysis and bound -> exit 0.

### Valid external gate or intentional wait

Input contains machine-represented release/closure -> report preserves gate/wait disposition without
upgrading bounded/inconclusive model truth -> exit 0.

### Invalid input

Duplicate key, non-finite value, unknown field, invalid reference, impossible gate, unsupported
fairness, or malformed JSON -> bounded refusal, no assurance report -> exit 2.

### Internal failure

Unexpected checker failure -> no proof or healthy default; bounded refusal unless a complete validated
report already exists -> exit 3.

## 15. Acceptance tests and proof

Required evidence on one immutable head:

1. all focused model/report/checker/CLI tests pass;
2. all mutation/falsifier tests pass;
3. fixed generated-at permutation test produces byte-identical reports;
4. no-side-effect test denies network, socket, subprocess, telemetry, SQLite, filesystem write, and
   source-owner access;
5. every hostile/valid fixture emits the frozen verdict/applicability/disposition/recommendation;
6. unsafe valid fixture exits 0;
7. invalid input exits 2 without traceback;
8. complete repository CI and CodeQL are green;
9. exact changed paths match Section 4 and contain no owner/runtime path;
10. direct Sol review maps every plan requirement to implementation and evidence.

Green CI alone is not completion. A1 completion establishes a real deterministic CLI capability, but
not current source applicability, Control Room product, runtime conformance, canary, or enforcement.

## 16. Stop condition

Stop when the exact A1 path set is implemented, every focused and repository gate is green on the
immutable head, direct Sol review accepts the user/machine journey, and the PR is merged at the
expected head.

Do not absorb OLS-A2 source compilation, Steward gather work, current status, Control Room UI,
calibration, canary, runtime monitoring, or enforcement.

## 17. Continuation handoff

Return:

```text
operation_key
branch
PR
exact head SHA
protected pickup SHA
changed paths
focused test commands and counts
repository CI/check receipts
fixture outcome matrix
mutation/falsifier evidence
no-side-effect evidence
known gaps
capability state
what merge makes true
what remains NOT_BUILT
exact next action
```

The next action after accepted A1 is a separate OLS-A2 architecture/implementation decision using the
protected Executive Steward pure read core and a separately accepted bounded gather/source-compiler
seam. No worker self-starts it from this handoff.
