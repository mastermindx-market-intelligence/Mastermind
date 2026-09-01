# Operation Assurance Core Implementation Plan

**Operation:** `mastermind-operation-liveness-soundness-20260830-sol-001`  
**Wave:** `OLS-A1`  
**Owner:** bounded implementation worker under Sol acceptance  
**Capability target:** pure deterministic model parser, checker, immutable report, report-only CLI,
and hostile/valid fixture corpus

## CONTROLLING OLS-A1 IMPLEMENTATION NOTICE

The law, design, and original task examples preserve architecture and research history, but portions
of earlier examples are historical drafting residue. A fresh worker must **do not implement** any
older example that conflicts with the following sources. Read them in this exact precedence order
before writing the first test:

1. `docs/superpowers/specs/2026-08-30-operation-assurance-immutable-report-projection-clarification.md`
2. `docs/superpowers/specs/2026-08-30-operation-assurance-model-fidelity-counterexample-validation-amendment.md`
3. `docs/superpowers/specs/2026-08-30-operation-assurance-a1-trusted-input-total-proof-clarification.md`
4. `docs/superpowers/specs/2026-08-30-operation-assurance-a1-controlling-execution-overlay.md`

Also read the current owner boundaries:

- `docs/superpowers/specs/2026-08-31-operation-liveness-soundness-executive-steward-reconciliation.md`
- `docs/superpowers/specs/2026-08-31-operation-liveness-soundness-sol-capability-fabric-reconciliation.md`
- `docs/superpowers/specs/2026-08-30-operation-liveness-soundness-runtime-observability-reconciliation.md`

This file is the executable navigation layer. The subject-specific sources above win where more
precise. No example from a lower-precedence source can silently reintroduce a withdrawn field,
trusted authored evidence, strong fairness, transitionless gate, incomplete proof, or duplicate
owner.

## 1. Observable mission

Given one authored closed `mastermind.operation_assurance_model.v1` JSON document, the CLI validates
it exactly, deterministically checks the reachable finite model within declared and hard safety
ceilings, and emits one canonical immutable `mastermind.operation_assurance_report.v1` with a
minimal source-attributed witness for every failed property and no runtime side effect.

A valid unsafe model still produces a report and normal CLI process completion.

## 2. Why this wave matters

OLS-A1 is the first independently useful Operation Assurance capability:

```text
authored model
-> exact parser
-> deterministic finite checker
-> immutable report
-> real report-only CLI consumer
-> hostile and valid fixtures
```

It turns architecture into machine behavior without pretending authored data is current production
truth. It establishes the correctness substrate required before a live-source compiler, Control Room
experience, calibration, canary, or promotion can exist.

## 3. Route and ownership

**Preferred avenue:** `CTO Sol`  
**Receiver binding:** `CAPACITY_SELECTABLE`  
**Why:** the wave is bounded but reasoning-heavy: finite-state semantics, canonical identity,
fairness, minimization, and proof ceilings must agree exactly.  
**Why not Fable:** the architecture and owner boundaries are frozen; no unresolved principal-level
cross-repository ambiguity belongs in A1.

The worker receives no merge, release, production, Executive, provider, or organizational authority
from this route label.

## 4. Exact repository and file map

Repository: `mastermindx-market-intelligence/Mastermind`

Create only:

| Path | Responsibility |
|---|---|
| `control_plane/operation_assurance_model.py` | closed model values, strict parser, validation, canonicalization, model identity |
| `control_plane/operation_assurance_report.py` | immutable report values, exact nested wire, validation, canonical identity |
| `control_plane/operation_assurance_checker.py` | reachability, generic properties, SCC/fairness products, witnesses, verdict composition |
| `scripts/operation_assurance.py` | bounded report-only JSON CLI |
| `tests/test_operation_assurance_model.py` | grammar, strict JSON, canonical identity, bounds, hostile parsing |
| `tests/test_operation_assurance_report.py` | exact report wire, identities, cross-axis anti-inflation |
| `tests/test_operation_assurance_checker.py` | safety, workflow, liveness, fairness, bounds, witnesses |
| `tests/test_operation_assurance_cli.py` | real machine-consumer and error-boundary contract |
| `tests/fixtures/operation_assurance/*.json` | frozen safe, unsafe, bounded, gated, recurring, and hostile models |

No edits to Executive Runtime, Executive Steward, Wake, SessionTarget, RuntimeBinding, Model Router,
watcher, Agent OS, Control Room, Runtime Observability, Sol Capability Fabric, Project Workroom,
Worker Browser, GitHub action code, deployment, provider, credential, or production-host paths are
allowed in OLS-A1.

## 5. Explicit non-goals

OLS-A1 does not:

- gather or compile live Executive OS, Agent OS, Wake, RuntimeBinding, Capacity, GitHub, Slack, or
  observability facts;
- create a source compiler, source cache, federated reader, Steward extension, or graph database;
- create or mutate lifecycle, admission, retry, placement, Wake, carrier, worker, session, lease,
  effect, or authority state;
- emit current assurance status;
- claim production applicability;
- perform source-contract or runtime-event replay;
- support strong fairness; strong fairness is outside OLS-A1;
- expose a web UI or Control Room card;
- block, admit, merge, deploy, retry, wake, or repair an operation;
- execute any repair candidate.

OLS-A1 stops at a pure report-only CLI.

## 6. Technology and purity boundary

- Python 3.11+
- production modules use the standard library only
- pytest is test-only
- frozen dataclasses or equivalent immutable value objects
- no production randomness
- no dynamic imports
- no network, socket, subprocess, telemetry, SQLite, filesystem write, source-owner, browser,
  provider, GitHub, Slack, or runtime I/O in model/report/checker modules
- the CLI reads exactly one explicit path or stdin and writes one report to stdout
- the CLI performs no write other than stdout/stderr
- invalid input exits 2
- internal checker/report refusal exits 3
- valid safe, unsafe, bounded, or inconclusive reports exit 0

The core must remain import-safe and side-effect-free.

## 7. Strict input boundary and hard resource ceilings

The CLI enforces hard ceilings before model semantics:

```text
MAX_INPUT_BYTES = 4194304
MAX_JSON_DEPTH = 64
MAX_TOTAL_JSON_NODES = 200000
MAX_TEXT_CHARS = 4096
MAX_TOKEN_CHARS = 128
MAX_STATE_VARIABLES = 128
MAX_DOMAIN_VALUES_PER_VARIABLE = 128
MAX_TOP_LEVEL_COLLECTION_ITEMS = 2048
MAX_NESTED_COLLECTION_ITEMS = 256
MAX_GUARDS_PER_OBJECT = 128
MAX_EFFECTS_PER_TRANSITION = 128
MAX_EXPLORATION_STATES = 1000000
MAX_EXPLORATION_DEPTH = 100000
```

A model's declared `max_states` and `max_depth` must be inside these hard ceilings. No caller can
request an unbounded search.

UTF-8 decoding is strict. The CLI rejects a byte-order mark, invalid UTF-8, oversized input, trailing
non-whitespace data, non-object top level, excessive depth, excessive nodes, and any collection or
text value above its ceiling.

Use `json.loads` with a duplicate-key rejecting `object_pairs_hook` and a non-finite-number rejecting
`parse_constant`. `NaN`, `Infinity`, and `-Infinity` are invalid JSON for OLS even if Python's parser
would otherwise accept them.

The parser does not silently coerce strings, booleans, integers, nulls, arrays, or mappings. In
particular, booleans are never accepted as integers.

## 8. Lexical boundary: open tokens versus closed semantics

### 8.1 Bounded canonical-token fields

These fields are bounded canonical ASCII tokens or token arrays:

- `transition.kind`
- `transition.actor_class`
- `transition.authority_requirement`
- `transition.progress_tags`
- `obligation.kind`
- `owner_or_authority`
- `source.owner`
- `source.source_kind`
- IDs and reason codes not otherwise declared as a closed enum

Canonical tokens match:

```text
[A-Z][A-Z0-9_]{0,127}
```

Stable object IDs additionally permit lowercase letters, digits, `.`, `:`, `/`, `_`, and `-`, must
start with an alphanumeric character, and are at most 128 characters.

Open tokens carry no checker privilege by their spelling. The generic checker does not infer that
`MODIFY`, `CHAIRMAN`, `WORKER`, `TERMINAL_PROGRESS`, `EFFECT_UNKNOWN`, or any other token grants
authority, implies progress, proves a source, or selects a policy. It compares open tokens only where
the closed model explicitly asks it to, such as a transition-forbidden authored safety property.

Descriptive text is bounded UTF-8, already Unicode NFC, has no C0 control characters, and has no
leading or trailing whitespace. The parser rejects rather than silently normalizes non-canonical
text.

State-domain values are bounded canonical Unicode strings only. Restricting state values to strings
prevents Python equality collisions such as `true == 1` and keeps state fingerprints portable.

### 8.2 Closed semantic enums

The parser validates exact closed values for fields whose spelling changes checker semantics:

```text
guard op:
EQ | NEQ | IN | NOT_IN

source freshness:
FRESH | STALE | UNKNOWN

source conflict:
NONE | CONFLICT | UNKNOWN

source coverage:
COMPLETE | PARTIAL | UNKNOWN

abstraction kind:
DECLARED_EXACT | SOUND_OVERAPPROXIMATION | TRACE_BACKED_UNDERAPPROXIMATION |
HEURISTIC_ABSTRACTION | UNKNOWN_FIDELITY

introduced/excluded behavior:
NONE_DECLARED | MAY_EXIST | KNOWN_PRESENT | UNKNOWN

validation kind:
AUTHOR_DECLARATION | SOURCE_COMPILER_ATTESTATION | SOURCE_CONTRACT_REPLAY |
RUNTIME_EVENT_REPLAY | INDEPENDENT_FORMAL_EQUIVALENCE | NONE

gate disposition:
EXTERNAL_GATE | INTENTIONAL_WAIT

fairness kind:
WEAK

terminal outcome kind:
TERMINAL_SUCCESS | TERMINAL_REFUSAL | TERMINAL_CANCELLED | TERMINAL_FAILED_SAFE

recurring outcome kind:
RECURRING_PROGRESS

safety property kind:
STATE_FORBIDDEN | TRANSITION_FORBIDDEN

property status:
PASS | FAIL | UNKNOWN | NOT_APPLICABLE
```

`NONE` fairness is represented by absence of an assumption. Strong fairness is rejected.

## 9. Exact model wire

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

### 9.1 Operation reference

```text
operation_key
root_job_id|null
pre_admission_identity|null
```

Exactly one of `root_job_id` and `pre_admission_identity` is non-null. This is analysis identity, not
runtime authority.

### 9.2 Compiler descriptor

```text
name
version
invocation_mode
```

`invocation_mode` must equal `AUTHORED_INPUT`. A1 has no trusted compiler or replay mode.

### 9.3 Source snapshot

```text
schema
sources[]
snapshot_hash
```

Each source contains exactly:

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

`source_identity` is unique. Every source/validation reference elsewhere in the model resolves to one
source identity.

`snapshot_hash` is SHA-256 over the canonical normalized object containing `schema` and `sources`,
excluding `snapshot_hash` itself.

Positive authored labels never grant current attestation. A1 generation-time applicability uses this
deterministic weakening order:

```text
CONFLICTED > STALE > INCOMPLETE > UNKNOWN > AUTHOR_DECLARED_ONLY
```

- any source `conflict=CONFLICT` -> `CONFLICTED`;
- otherwise any `freshness=STALE` -> `STALE`;
- otherwise any `coverage=PARTIAL`, `truncated=true`, or required continuation -> `INCOMPLETE`;
- otherwise any unknown freshness/conflict/coverage -> `UNKNOWN`;
- otherwise -> `AUTHOR_DECLARED_ONLY`.

A1 cannot emit `CURRENT_SOURCE_ATTESTED` or `HISTORICAL_SOURCE_ATTESTED`.

### 9.4 Abstraction contract

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

Authored validation labels are descriptive only. `DECLARED_EXACT` can support proof only inside the
declared model. Under-approximation cannot prove absence. Over-approximation may prove preserved
absence but its witness is potentially spurious until separately validated. Heuristic or unknown
fidelity cannot support proof.

### 9.5 State domains and initial state

- each variable ID is unique;
- each domain is a finite non-empty sequence of unique canonical strings;
- the initial-state key set exactly equals the domain key set;
- every initial value belongs to its declared domain;
- variable order is lexical and stable.

A state is the tuple of values in lexical variable order. `state_fingerprint` is SHA-256 over the
canonical variable-to-value mapping.

### 9.6 Guards and effects

Guard fields:

```text
variable
op
value
```

`EQ` and `NEQ` use one scalar domain value. `IN` and `NOT_IN` use a non-empty unique sequence of
domain values.

Effect fields:

```text
variable
value
```

Effects are simultaneous assignments. Duplicate effects for one variable are refused rather than
ordered.

### 9.7 Transitions

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
gate_refs[]
required_reachable
```

`gate_refs` is a sorted unique list. Gate `release_transition_ids` and transition `gate_refs` agree
bidirectionally: a transition names a gate exactly when that gate names the transition.

Fairness and environment references also agree bidirectionally. One-sided or mismatched references
are parser refusal.

`actor_class`, `authority_requirement`, and `progress_tags` are explanation/provenance metadata only
in A1. They grant no authority and cannot substitute for authored state/transition safety
properties, terminal/recurring outcomes, obligations, resources, or gates.

### 9.8 Outcomes

Terminal outcome:

```text
outcome_id
kind
guards[]
owned_persistent_obligation_ids[]
owned_persistent_resource_ids[]
source_refs[]
```

Recurring outcome has the same fields but `kind=RECURRING_PROGRESS` and lives only in
`recurring_progress_outcomes`.

Terminal outcomes cannot own non-persistent residue. All owned IDs resolve and identify persistent
objects.

### 9.9 Obligations

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

Pending and discharged sets are non-empty, disjoint, and inside the declared domain.

### 9.10 Resources

```text
resource_id
holder_variable
released_values[]
persistent
owner_or_authority
source_refs[]
```

Released values are non-empty and inside the declared domain. Any other value is held.

### 9.11 Gates and waits

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

`release_transition_ids` is non-empty. `escalation_or_close_path` names one listed transition.
Every release transition is enabled in at least one reachable gate state and either reaches a
continuing state or matches a named terminal outcome. A syntactically valid but unreachable return
path is a failed generic property, not a valid gate.

Transitionless terminal-boundary prose is refused.

### 9.12 Fairness assumptions

```text
fairness_id
kind = WEAK
transition_ids[]
source_refs[]
```

The transition list is non-empty. Each transition has the matching `fairness_ref`. Weak fairness can
exclude only a candidate closed walk where a named transition is enabled in every visited cycle state
and never taken.

### 9.13 Environment assumptions

```text
assumption_id
kind
transition_ids[]
required_for_property_ids[]
source_refs[]
```

Each transition has the matching `external_assumption_ref`. An external or human event assumption is
a model premise, not scheduler fairness or a promise the event will occur.

### 9.14 Authored safety properties

State-forbidden:

```text
property_id
kind = STATE_FORBIDDEN
violation_when[]
source_refs[]
```

Transition-forbidden:

```text
property_id
kind = TRANSITION_FORBIDDEN
when[]
forbidden_transition_kinds[]
source_refs[]
```

Mixed shapes, empty forbidden kind sets, or IDs colliding with generic mandatory properties are
refused.

### 9.15 Model gaps

```text
gap_id
reason
load_bearing
affects_property_ids[]
affects_transition_ids[]
affects_variable_ids[]
source_refs[]
```

Every affected identity resolves. Empty affected arrays are legal only for a non-load-bearing gap
whose reason explicitly states why no checked property can change.

### 9.16 Exploration limits

```text
max_states
max_depth
```

Both are exact non-negative integers, not booleans. `max_states >= 1`; both remain inside the hard
ceilings in Section 7.

## 10. Deterministic normalization

Semantically unordered collections are normalized before hashing or analysis. Reject duplicate IDs
or duplicate set members before sorting; never silently coalesce them.

Normalize:

- state-domain keys lexically and domain values by canonical bytes;
- sources by source_identity;
- transitions by transition_id;
- terminal and recurring outcomes by outcome_id;
- obligations by obligation_id;
- resources by resource_id;
- gates by gate_id;
- fairness assumptions by fairness_id;
- environment assumptions by assumption_id;
- authored safety properties by property_id;
- model gaps by gap_id;
- guards by canonical bytes;
- effects by variable;
- set-like IDs, source refs, validation refs, tokens, and reason codes lexically;
- property_results by property_id;
- counterexamples by property_id then counterexample_id;
- repair candidates by repair_id;
- analysis products by analysis_id.

Trace order is never sorted. `shortest_prefix`, `cycle`, state deltas, and transition-reason snapshots
remain execution order.

Canonical JSON uses:

```python
json.dumps(
    value,
    sort_keys=True,
    separators=(",", ":"),
    ensure_ascii=False,
    allow_nan=False,
)
```

## 11. Exact exploration-bound semantics

- the initial state is depth 0;
- the initial state counts toward max_states;
- a discovered state is retained even when it is at the depth ceiling;
- a state at max_depth is retained but not expanded to a new unseen successor;
- enabled/disabled transition reasons and transition-forbidden safety are still evaluated at the
  depth ceiling;
- edges to already discovered states, including self-loops, are still materialized at the depth
  ceiling;
- a successor that would exceed max_states is not inserted;
- edges to already discovered states are still materialized after the state ceiling is reached;
- any withheld legal unseen successor makes `base_graph_complete=false`;
- every exact withheld reason is recorded;
- a complete definite witness already materialized before a later bound is preserved;
- each fairness/property product is separately bounded by the model's `max_states` and reports
  `FAIRNESS_PRODUCT_STATE_LIMIT_REACHED` or its exact product reason.

No wall-clock timeout is part of the canonical model. Host timeout or memory failure is an internal
checker refusal, never a bounded proof result.

## 12. Generic checker versus Mastermind policy

### 12.1 Generic mandatory property IDs

The A1 engine always evaluates:

```text
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

These properties derive only from the closed generic model: states, transitions, outcomes,
obligations, resources, gates, and assumptions.

`NO_EFFECT_UNKNOWN_ESCAPE and ONE_ACTION_AUTHORITY are explicit authored safety property IDs`, not
hidden hard-coded interpretations of variable or token names. A fixture that tests those Mastermind
laws must include exact authored state/transition safety properties and the required state variables.

The A2 source compiler, not the generic A1 checker, decides which Mastermind policy properties a real operation must contain. The compiler must fail closed when a real operation class lacks a required
policy property. This keeps current organizational policy out of the generic checker while ensuring
compiled real models cannot omit it.

The law's identity/authority and effect/retry families are therefore requirements for real compiled
models and fixtures, not permission for A1 to infer semantics from labels such as `EFFECT_UNKNOWN`,
`MODIFY`, `SOL`, or `CHAIRMAN`.

Authored property IDs are reported separately from generic mandatory IDs and cannot suppress or
replace them.

## 13. Exact immutable report wire

The highest-precedence exact top-level and nested report contract is
`docs/superpowers/specs/2026-08-30-operation-assurance-immutable-report-projection-clarification.md`.

Top-level fields are:

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

The report contains no `assurance_verdict`, `current_projection_verdict`, bare
`source_applicability`, current status, current recommendation, current source receipts,
recomputation time, or wall-clock duration.

Report identity:
- canonicalize the body excluding `report_id` and `report_hash`;
- hash with SHA-256;
- `report_id = "oar_" + report_hash[:24]`.

Counterexample identity:
- canonicalize `model_hash` plus the counterexample body excluding `counterexample_id`;
- hash with SHA-256;
- `counterexample_id = "ocx_" + counterexample_hash[:24]`.

Fixed model plus fixed UTC `generated_at` produces byte-identical output.

## 14. Generic algorithms and property semantics

### 14.1 Reachability

Use deterministic BFS from the initial state. Transition iteration is lexical. Record one canonical
shortest predecessor; when multiple same-depth predecessors exist, choose the lexically smallest
transition sequence, then state fingerprint.

The graph stores reached states, materialized edges, enabled transition IDs, disabled transition
reasons, first depth, canonical predecessor, and completion/bound receipts.

### 14.2 Authored safety properties

Evaluate state-forbidden properties on every reached state. Evaluate transition-forbidden properties
on every enabled outgoing transition before deciding whether an unseen successor can be inserted.
A definite violation receives the shortest prefix under the canonical tie-break.

### 14.3 Option to complete

Reverse graph analysis marks states that can reach:
- a terminal outcome;
- a valid external gate;
- a valid intentional wait;
- an accepted recurring outcome.

A state outside an accepted gate/wait/recurring outcome that cannot reach one of these boundaries
fails `OPTION_TO_COMPLETE`.

### 14.4 Proper completion

Every reached terminal outcome must:
- be absorbing;
- have no pending non-persistent obligation;
- have no held non-persistent resource;
- own every remaining persistent obligation/resource explicitly;
- satisfy all authored terminal safety properties.

Failure uses the shortest prefix to the terminal state.

### 14.5 Dead required transition

Every transition with `required_reachable=true` must occur on at least one materialized reachable
edge. In a complete graph, absence is `FAIL` with a deterministic `GLOBAL_CERTIFICATE`. In an
incomplete graph where the transition could exist beyond a withheld successor, the result is
`UNKNOWN`.

### 14.6 Terminal absorption

For every reached terminal state, evaluate all outgoing transitions. Any enabled operation transition
fails `NO_POST_TERMINAL_TRANSITION`. Logical model-checker stuttering is not an operation transition.

### 14.7 Gate/wait return path

For each reached gate state, at least one named release transition must be enabled and its materialized
successor must leave the gate or match a named terminal outcome. Complete proof of no valid return is
`FAIL`; withheld successor/bound is `UNKNOWN`.

### 14.8 Universal progress

Analyze all reachable cyclic SCCs, not only closed SCCs. A fairness-valid closed walk that avoids
terminal outcomes, valid gates/waits, and accepted recurring progress fails `UNIVERSAL_PROGRESS`.
This synthetic root progress property applies even when the model declares no obligations.

### 14.9 Weak-fair closed-walk product

For each candidate violating entry state, BFS over:

```text
(graph_state, seen_or_disabled_fairness_mask, violation_progress_mask)
```

A return to the entry is accepted only when:
- the violating condition remains true;
- every named weak-fair transition is either taken or disabled in at least one visited cycle state;
- the cycle is non-empty.

This search may combine multiple simple cycles. Tie-break by shortest prefix + cycle length,
transition sequence, then state fingerprints.

### 14.10 Fairness realizability

`FAIRNESS_REALIZABLE` is:
- `NOT_APPLICABLE` when no fairness assumption exists;
- `PASS` only when every referenced transition occurs on at least one materialized edge in the
  complete relevant graph and every assumption has at least one reachable enabling state;
- `FAIL` when complete analysis proves an assumption transition never enables or can never occur;
- `UNKNOWN` when a bound could hide the required evidence.

A vacuous or impossible fairness assumption cannot exclude all violating executions or manufacture
proof.

### 14.11 Recurring progress

`RECURRING_PROGRESS_VALID` is:
- `NOT_APPLICABLE` when no recurring outcome exists;
- `PASS` when every reached recurring state has an executable recurrence or continuing progress path,
  owns only declared persistent residue, and no authored safety property fails;
- `FAIL` when complete analysis proves a declared recurring outcome is fake terminal residue or cannot
  recur/continue;
- `UNKNOWN` when a bound prevents the determination.

Progress tags alone are not recurring evidence.

### 14.12 Starvation

`NO_STARVATION_UNDER_DECLARED_FAIRNESS` is:
- `NOT_APPLICABLE` when no persistent obligation exists;
- `FAIL` when a fairness-valid lasso keeps one persistent obligation pending forever without accepted
  recurring progress or legal ownership transfer;
- `PASS` when complete product analysis finds no such lasso;
- `UNKNOWN` when a relevant product is incomplete.

### 14.13 Minimal witnesses

Safety/workflow traces minimize prefix length. Liveness/starvation witnesses minimize prefix + cycle
length. Global absence defects use `GLOBAL_CERTIFICATE`.

Every witness includes initial state, ordered transition IDs, state deltas, enabled/disabled reasons,
source refs, realizability, relevant gaps, non-executable repair candidates, and limitations.

## 15. Verdict, applicability, disposition, and recommendation

### 15.1 Model-analysis verdict

1. a fully materialized definite witness with no relevant invalidating gap ->
   `UNSAFE_COUNTEREXAMPLE`;
2. a potentially spurious witness, unknown fidelity, or relevant load-bearing gap ->
   `INCONCLUSIVE_MODEL_GAP` with the candidate retained;
3. all finite domains, complete graph, every load-bearing analysis complete, every generic/authored
   property `PASS` or legally `NOT_APPLICABLE`, property-preserving abstraction, and normal
   termination -> `PROVEN_WITHIN_FINITE_MODEL`;
4. a declared state/depth/product bound reached with no definite witness ->
   `BOUNDED_NO_COUNTEREXAMPLE` unless a model/fidelity gap requires inconclusive;
5. otherwise -> `INCONCLUSIVE_MODEL_GAP`.

A complete definite witness is not erased by an unrelated later bound. An internal exception never
returns a healthy default.

### 15.2 Progress disposition

Use this deterministic precedence:

```text
NO_PROGRESS
EXTERNALLY_GATED
INTENTIONAL_WAIT
RECURRING_SERVICE
FAIRNESS_CONDITIONAL
AUTONOMOUSLY_LIVE
UNKNOWN
```

- `NO_PROGRESS` requires a failed progress/starvation/option-to-complete property;
- external gate or wait requires a reached valid contract;
- recurring service requires a reached valid recurring outcome;
- fairness conditional requires otherwise passing progress that depends on at least one weak fairness
  assumption;
- autonomous live requires complete passing progress without a gate/wait/recurring/fairness
  dependency;
- bounded/incomplete cases not otherwise classified use `UNKNOWN`.

A disposition never upgrades the model verdict.

### 15.3 A1 recommendation

Use this precedence:

1. source `CONFLICTED` or `STALE` -> `REPORT_ONLY_RECONCILE`;
2. definite unsafe witness -> `REPORT_ONLY_REPAIR`;
3. complete valid external gate or intentional wait with no failed property ->
   `REPORT_ONLY_AWAIT_GATE`;
4. every other A1 result -> `REPORT_ONLY_NO_RECOMMENDATION`.

OLS-A1 never emits `REPORT_ONLY_PROCEED`.

## 16. Exact `NOT_APPLICABLE` law

`NOT_APPLICABLE` is legal only for:
- `RECURRING_PROGRESS_VALID` when no recurring outcome is declared;
- `NO_STARVATION_UNDER_DECLARED_FAIRNESS` when no persistent obligation is declared;
- `FAIRNESS_REALIZABLE` when no fairness assumption is declared.

Every other generic mandatory property and every authored safety property must be `PASS`, `FAIL`, or
`UNKNOWN`.

## 17. Ordered TDD implementation sequence

### Task 0 — isolated pickup and baseline

- create an isolated worktree/branch from the exact accepted protected F0 descendant;
- collision-check every path in Section 4 and all current PRs;
- run the complete repository test gate before changes;
- stop on a dirty or unexplained failing baseline.

### Task 1 — strict JSON, model grammar, and identity

RED first:
- strict UTF-8 and input size;
- duplicate-key `object_pairs_hook`;
- non-finite `parse_constant`;
- depth/node/collection/text ceilings;
- exact keys and closed enums;
- open-token no-privilege behavior;
- required abstraction contract;
- source/snapshot identity;
- cross-reference and bidirectional gate/fairness/environment links;
- canonical model hash under input permutations.

GREEN:
- immutable model values;
- strict loader helper;
- exact parser and semantic validation;
- normalization and canonical helpers.

Focused verification:

```bash
pytest -q tests/test_operation_assurance_model.py
```

### Task 2 — exact immutable report

RED first:
- exact top-level and nested fields;
- property/counterexample/coverage/assumption/exploration shapes;
- narrow `NOT_APPLICABLE`;
- non-circular report and counterexample identities;
- UTC generated-at validation;
- orthogonal axes;
- no current fields or duration;
- cross-field anti-inflation.

GREEN:
- immutable report values;
- exact validator/finalizer;
- canonical serialization.

Focused verification:

```bash
pytest -q tests/test_operation_assurance_report.py
```

### Task 3 — reachability and transition semantics

RED first:
- lexical transition iteration and same-depth tie-break;
- simultaneous effects;
- self-loops and existing-state edges at bounds;
- exact state/depth semantics in Section 11;
- terminal states retained for absorption checks;
- deterministic enabled/disabled reasons.

GREEN:
- transition evaluator;
- immutable reachability graph;
- bounded BFS and receipts.

### Task 4 — authored safety and workflow soundness

RED first:
- state-forbidden and transition-forbidden properties;
- fixture-authored `NO_EFFECT_UNKNOWN_ESCAPE`;
- fixture-authored `ONE_ACTION_AUTHORITY`;
- option to complete;
- proper terminal residue;
- dead required transition;
- gate/wait return path;
- cancellation/refusal terminals;
- post-terminal transition.

GREEN:
- deterministic property evaluators;
- reverse completion;
- terminal/gate checks;
- minimal trace/global certificates.

### Task 5 — liveness, weak fairness, recurring progress, and starvation

RED first:
- non-progress self-loop with outgoing completion edge;
- weak fairness excludes only continuously enabled untaken transition;
- transition disabled in one cycle state does not trigger weak fairness;
- fair violating closed walk combining multiple simple cycles;
- vacuous/unrealizable fairness cannot manufacture proof;
- empty obligation list cannot hide root livelock;
- persistent-obligation starvation;
- valid recurring progress;
- fake recurring progress;
- fairness-product state limit.

GREEN:
- SCC enumeration;
- seen-or-disabled fairness product;
- recurring and starvation analysis;
- shortest deterministic lassos.

### Task 6 — final composition

RED first:
- base BFS complete while product incomplete cannot prove;
- unknown generic/authored property cannot prove;
- relevant gap weakens witness/proof;
- unrelated non-load-bearing gap does not hide a definite witness;
- under-approximate no-witness cannot prove;
- complete definite witness survives unrelated later bound;
- internal exception refuses rather than returning healthy output;
- applicability, disposition, and recommendation precedence.

GREEN:
- final report composition;
- per-analysis coverage;
- bounded/inconclusive/unsafe preservation.

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

CLI:

```text
operation-assurance MODEL.json [--pretty]
operation-assurance - [--pretty]
```

No flag may request trusted source mode, replay mode, admission, mutation, retry, Wake, placement,
GitHub, browser, provider, or runtime action.

Exit contract:
- 0 valid report, including unsafe/bounded/inconclusive;
- 2 invalid JSON or refused model;
- 3 internal checker/report refusal.

Errors are one bounded line and contain no traceback or absolute local path by default.

### Task 8 — adversarial fence

Tests must kill at least these mutations:

1. accept unknown fields;
2. accept duplicate JSON keys;
3. accept NaN/Infinity;
4. exceed resource ceilings;
5. trust authored source/compiler/replay labels;
6. infer semantic privilege from an open token;
7. omit abstraction contract;
8. allow one-sided gate/fairness/environment references;
9. order duplicate effects;
10. treat progress tags as recurring evidence;
11. suppress generic mandatory properties;
12. hardcode Mastermind-specific token semantics in the generic checker;
13. limit liveness to closed SCCs;
14. search only simple cycles;
15. treat weak fairness as strong fairness;
16. accept vacuous fairness;
17. prove after an incomplete product;
18. erase a definite witness after a later bound;
19. permit post-terminal transitions;
20. accept descriptive gate prose without modeled return;
21. compute report or counterexample identity circularly;
22. include duration in canonical output;
23. emit current status from A1;
24. emit `REPORT_ONLY_PROCEED`;
25. allow illegal `NOT_APPLICABLE`;
26. sort a trace rather than preserving execution order;
27. return non-zero for a valid unsafe report;
28. perform network, socket, subprocess, telemetry, SQLite, filesystem-write, runtime, or source-owner
    I/O in the core.

## 18. Complete machine journeys

### Safe finite model

Input parses -> every generic and authored property completes -> report emits
`PROVEN_WITHIN_FINITE_MODEL + AUTHOR_DECLARED_ONLY + AUTONOMOUSLY_LIVE +
REPORT_ONLY_NO_RECOMMENDATION` -> exit 0.

### Definite authored unsafe model

Input parses -> shortest witness completes -> report emits
`UNSAFE_COUNTEREXAMPLE + DECLARED_MODEL_ONLY + NO_PROGRESS + REPORT_ONLY_REPAIR` -> exit 0.

### Potentially spurious model

Input parses -> candidate witness found under over-approximation/relevant gap -> report retains
`POTENTIALLY_SPURIOUS + INCONCLUSIVE_MODEL_GAP + REPORT_ONLY_NO_RECOMMENDATION` -> exit 0.

### Bounded analysis

Input parses -> declared bound prevents complete no-witness proof -> report identifies exact
incomplete graph/product and emits bounded or inconclusive result -> exit 0.

### External gate or intentional wait

Input contains a complete machine-represented return/closure path -> report preserves
`EXTERNALLY_GATED` or `INTENTIONAL_WAIT` and `REPORT_ONLY_AWAIT_GATE` without claiming autonomous
liveness -> exit 0.

### Recurring service

Input contains an accepted recurring outcome and lawful persistent ownership -> recurring property
passes and disposition is `RECURRING_SERVICE` without forcing terminal completion -> exit 0.

### Invalid input

Malformed JSON, duplicate key, non-finite number, resource-ceiling breach, unknown field, invalid
reference, impossible gate, unsupported fairness, or non-canonical text -> bounded refusal, no report
-> exit 2.

### Internal failure

Unexpected checker/report failure -> no proof or healthy default -> bounded refusal unless a complete
validated immutable report had already been finalized -> exit 3.

## 19. Acceptance evidence

One immutable candidate head must prove:

1. all focused model/report/checker/CLI tests pass;
2. all adversarial mutation/falsifier tests pass;
3. permutation tests produce byte-identical model/report output at fixed `generated_at`;
4. no-side-effect tests deny network, socket, subprocess, telemetry, SQLite, filesystem write, and
   source-owner access;
5. every fixture emits the frozen verdict/applicability/disposition/recommendation;
6. valid unsafe fixture exits 0;
7. invalid input exits 2 without traceback;
8. internal refusal exits 3;
9. complete repository CI and CodeQL are green;
10. exact changed paths match Section 4 and contain no protected owner/runtime path;
11. direct Sol review maps every requirement to implementation and evidence.

Green CI alone is not completion. A1 completion establishes a real deterministic CLI capability, but
not current source applicability, Control Room product, runtime conformance, canary, enforcement, or
production acceptance.

## 20. Stop condition

Stop when the exact A1 path set is implemented, every focused/adversarial/repository gate is green on
the immutable head, the complete machine journeys work, direct Sol review accepts the result, and the
PR is merged at the expected head.

Do not absorb OLS-A2 source compilation, Steward gather work, current status, Control Room UI,
calibration, canary, runtime monitoring, or enforcement.

## 21. Continuation handoff

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

After accepted A1, OLS-A2 is a separate one-real-operation source-compiler vertical using the
protected Executive Steward pure read core plus a separately accepted bounded gather/source-compiler
seam. No worker self-starts it from this handoff.
