# Operation Assurance Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a pure, deterministic, report-only finite-state Operation Assurance core that validates a closed model, explores all reachable states within explicit bounds, and returns minimal source-attributed safety or liveness counterexamples without reading or mutating any Mastermind runtime owner.

**Architecture:** A closed JSON model is parsed into immutable dataclasses. A standard-library explicit-state checker performs deterministic breadth-first reachability, reverse completion analysis, strongly connected component/lasso analysis, weak-fairness filtering, and verdict composition. A CLI is the first real machine consumer and emits `mastermind.operation_assurance_report.v1`; canonical source compilation, Steward/Control Room integration, admission attachment, and runtime conformance are later waves.

**Tech Stack:** Python 3.11+, standard library only (`dataclasses`, `enum`, `hashlib`, `json`, `collections`, `datetime`, `argparse`, `pathlib`), pytest.

**Spec:** `docs/superpowers/specs/2026-08-30-operation-liveness-soundness-design.md`

## Global Constraints

- This plan implements **OLS-A1 only**. It does not compile live Executive/Agent OS/Wake/RuntimeBinding state.
- Create no database, lifecycle, queue, scheduler, watcher, retry, authority, session, worker, attention, or capacity owner.
- No edits to Executive Runtime, Executive Steward, Wake, SessionTarget, RuntimeBinding, Model Router, watcher, Agent OS, or Control Room paths are allowed in OLS-A1.
- V1 is report-only. A valid unsafe model still produces a report and normal CLI process completion.
- Use the exact schemas `mastermind.operation_assurance_model.v1` and `mastermind.operation_assurance_report.v1`.
- Use canonical UTF-8 JSON: sorted keys, separators `(",", ":")`, `ensure_ascii=False`, `allow_nan=False`.
- Unknown fields, opaque/executable guards, non-finite domains, duplicate identities, unresolved references, and values outside declared domains fail closed during parsing.
- Model-generated text has zero verdict authority.
- `PROVEN_WITHIN_FINITE_MODEL` requires complete reachable-state exploration and zero load-bearing model/source gaps.
- State/depth limits may only yield `BOUNDED_NO_COUNTEREXAMPLE`, `INCONCLUSIVE_MODEL_GAP`, or an unsafe counterexample already found.
- Strong fairness is outside OLS-A1. Support `NONE` and `WEAK` only.
- Counterexample ordering is deterministic: shortest path first, then canonical transition sequence, then state fingerprint.
- Use TDD. Each task ends with exact focused tests and a commit.
- Before implementation, create an isolated worktree from the exact accepted OLS-F0 protected descendant and collision-check the paths below.

## File map

| Path | Responsibility |
|---|---|
| `control_plane/operation_assurance_model.py` | closed model types, parser, validation, canonicalization and model hash |
| `control_plane/operation_assurance_report.py` | closed report/verdict/trace types and canonical serialization |
| `control_plane/operation_assurance_checker.py` | transition evaluation, reachable graph, properties, SCC/lasso, verdict composition |
| `scripts/operation_assurance.py` | report-only JSON CLI and error boundary |
| `tests/test_operation_assurance_model.py` | model grammar and hash tests |
| `tests/test_operation_assurance_report.py` | report-axis and serialization tests |
| `tests/test_operation_assurance_checker.py` | reachability, soundness, safety, liveness, fairness and bounds |
| `tests/test_operation_assurance_cli.py` | real machine-consumer contract |
| `tests/fixtures/operation_assurance/*.json` | frozen hostile and valid operation models |

---

### Task 1: Closed model grammar and canonical identity

**Files:**
- Create: `control_plane/operation_assurance_model.py`
- Create: `tests/test_operation_assurance_model.py`

**Interfaces:**
- Produces:
  - `MODEL_SCHEMA: str`
  - `PROPERTY_SET_V1: str`
  - `OperationAssuranceModelError(ValueError)`
  - immutable dataclasses `Guard`, `Effect`, `Transition`, `StateSafetyProperty`, `TransitionSafetyProperty`, `SafetyProperty`, `Obligation`, `Resource`, `Outcome`, `Gate`, `FairnessAssumption`, `SourceSnapshot`, `ExplorationLimits`, `OperationAssuranceModel`
  - `canonical_bytes(value: object) -> bytes`
  - `canonical_sha256(value: object) -> str`
  - `parse_model(document: Mapping[str, object]) -> OperationAssuranceModel`
  - `model_to_dict(model: OperationAssuranceModel) -> dict[str, object]`
  - `state_fingerprint(variable_order: tuple[str, ...], state: tuple[str, ...]) -> str`
- Consumed by Tasks 2–8.

- [ ] **Step 1: Write the minimal valid-model and canonical-hash tests**

Create a `_minimal_document()` fixture containing exactly:

```python
{
    "schema": "mastermind.operation_assurance_model.v1",
    "model_id": "oam_test_minimal",
    "operation_ref": {"operation_key": "test-operation-001", "root_job_id": None},
    "compiler": {"name": "fixture", "version": "1.0.0"},
    "source_snapshot": {
        "schema": "mastermind.operation_assurance_source_snapshot.v1",
        "sources": [{
            "owner": "github",
            "source_kind": "git_object",
            "source_identity": "Mastermind@0123456789abcdef0123456789abcdef01234567",
            "schema_version": "git/v1",
            "digest": "a" * 64,
            "effective_at": None,
            "observed_at": "2026-08-30T10:00:00Z",
            "correction_ref": None,
            "freshness": "FRESH",
            "conflict": "NONE",
        }],
        "snapshot_hash": "",
    },
    "state_domains": {
        "phase": ["START", "DONE"],
        "obligation.return": ["PENDING", "DISCHARGED"],
        "resource.worker": ["FREE", "HELD"],
    },
    "initial_state": {
        "phase": "START",
        "obligation.return": "PENDING",
        "resource.worker": "FREE",
    },
    "transitions": [{
        "transition_id": "complete",
        "kind": "PROGRESS",
        "actor_class": "WORKER",
        "authority_requirement": "COO_OR_WORKER",
        "guards": [{"variable": "phase", "op": "EQ", "value": "START"}],
        "effects": [
            {"variable": "phase", "value": "DONE"},
            {"variable": "obligation.return", "value": "DISCHARGED"},
        ],
        "progress_tags": ["TERMINAL_PROGRESS"],
        "source_refs": ["Mastermind@0123456789abcdef0123456789abcdef01234567"],
        "fairness_ref": None,
        "external_assumption_ref": None,
        "required_reachable": True,
    }],
    "terminal_outcomes": [{
        "outcome_id": "done",
        "kind": "TERMINAL_SUCCESS",
        "guards": [{"variable": "phase", "op": "EQ", "value": "DONE"}],
        "source_refs": ["Mastermind@0123456789abcdef0123456789abcdef01234567"],
    }],
    "recurring_progress_outcomes": [],
    "obligations": [{
        "obligation_id": "return",
        "kind": "RETURN",
        "state_variable": "obligation.return",
        "pending_values": ["PENDING"],
        "discharged_values": ["DISCHARGED"],
        "persistent": False,
        "source_refs": ["Mastermind@0123456789abcdef0123456789abcdef01234567"],
    }],
    "resources": [{
        "resource_id": "worker",
        "holder_variable": "resource.worker",
        "released_values": ["FREE"],
        "persistent": False,
        "source_refs": ["Mastermind@0123456789abcdef0123456789abcdef01234567"],
    }],
    "external_gates": [],
    "fairness_assumptions": [],
    "environment_assumptions": [],
    "safety_properties": [],
    "property_set": "mastermind.operation_assurance.properties.v1",
    "exploration_limits": {"max_states": 1000, "max_depth": 100},
    "known_model_gaps": [],
}
```

Compute `source_snapshot.snapshot_hash` with `canonical_sha256({"schema": ..., "sources": ...})`.
Assert parsing succeeds, variable order is lexical, and two documents with reversed mapping insertion
order produce the same `model_hash`.

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```bash
pytest -q tests/test_operation_assurance_model.py::test_minimal_model_parses_and_hash_is_canonical
```

Expected: import failure because `operation_assurance_model.py` does not exist.

- [ ] **Step 3: Implement immutable model types and canonical helpers**

Implement frozen dataclasses and:

```python
MODEL_SCHEMA = "mastermind.operation_assurance_model.v1"
SOURCE_SNAPSHOT_SCHEMA = "mastermind.operation_assurance_source_snapshot.v1"
PROPERTY_SET_V1 = "mastermind.operation_assurance.properties.v1"

def canonical_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise OperationAssuranceModelError(
            f"value is not canonical JSON data: {exc}"
        ) from exc

def canonical_sha256(value: object) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()
```

Keep all enum-like wire values as validated strings in closed `frozenset` constants so serialization
does not depend on Enum implementation details.

- [ ] **Step 4: Implement exact-key parsing and cross-reference validation**

Use explicit key sets for every object. Parsing must reject:

- unknown or missing keys;
- booleans where integers are required;
- empty or duplicate finite-domain values;
- initial-state keys not exactly equal to `state_domains`;
- a guard/effect variable not declared;
- a guard/effect value outside its variable domain;
- guard operators outside `EQ`, `NEQ`, `IN`, `NOT_IN`;
- sequence-valued guard operands for `EQ`/`NEQ` or scalar operands for `IN`/`NOT_IN`;
- duplicate transition/outcome/obligation/resource/gate/fairness/property IDs;
- missing transition, fairness, source or assumption references;
- fairness kinds outside `NONE`, `WEAK`;
- `max_states < 1` or `max_depth < 0`;
- non-empty `known_model_gaps` entries without `gap_id`, `reason`, `load_bearing`, and `source_refs`;
- source freshness outside `FRESH`, `STALE`, `UNKNOWN`;
- source conflict outside `NONE`, `CONFLICT`, `UNKNOWN`;
- supplied snapshot/model IDs that do not match their closed format.

Do not silently coerce strings, integers or nulls.

- [ ] **Step 5: Add hostile grammar tests**

Add parametrized tests that mutate the minimal document one defect at a time:

```python
@pytest.mark.parametrize("mutate, expected", [
    (lambda d: d.__setitem__("extra", True), "model fields mismatch"),
    (lambda d: d["state_domains"].__setitem__("unbounded", []), "domain must be non-empty"),
    (lambda d: d["transitions"][0]["guards"][0].__setitem__("op", "PYTHON"),
     "guard op is unsupported"),
    (lambda d: d["transitions"][0]["effects"][0].__setitem__("value", "MISSING"),
     "effect value is outside the declared domain"),
])
def test_model_rejects_closed_wire_violations(mutate, expected):
    document = _minimal_document()
    mutate(document)
    with pytest.raises(OperationAssuranceModelError, match=expected):
        parse_model(document)
```

Also assert `float("nan")`, `float("inf")`, sets, bytes, and control characters cannot enter a
canonical model.

- [ ] **Step 6: Run model tests**

Run:

```bash
pytest -q tests/test_operation_assurance_model.py
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add control_plane/operation_assurance_model.py tests/test_operation_assurance_model.py
git commit -m "feat(ols): add closed operation assurance model"
```

---

### Task 2: Closed report wire with orthogonal truth axes

**Files:**
- Create: `control_plane/operation_assurance_report.py`
- Create: `tests/test_operation_assurance_report.py`

**Interfaces:**
- Consumes: `canonical_sha256` and source/model identities from Task 1.
- Produces:
  - `REPORT_SCHEMA`, `CHECKER_VERSION`
  - closed string constants for verdict, disposition, recommendation and property status
  - frozen dataclasses `TraceStep`, `Counterexample`, `PropertyResult`, `ExplorationReceipt`, `OperationAssuranceReport`
  - `report_to_dict(report) -> dict[str, object]`
  - `finalize_report(..., generated_at: datetime) -> OperationAssuranceReport`

- [ ] **Step 1: Write report-axis tests**

Assert a report can represent:

```text
assurance_verdict = BOUNDED_NO_COUNTEREXAMPLE
progress_disposition = EXTERNALLY_GATED
admission_recommendation = REPORT_ONLY_AWAIT_GATE
```

without any field upgrading the verdict to proof. Assert `report_hash` is stable with a fixed UTC
`generated_at`, changes when exploration limits change, and rejects naive/offset-non-UTC datetimes.

- [ ] **Step 2: Run and verify RED**

```bash
pytest -q tests/test_operation_assurance_report.py
```

Expected: import failure.

- [ ] **Step 3: Implement report dataclasses and exact serialization**

Use these closed values:

```python
ASSURANCE_VERDICTS = frozenset({
    "UNSAFE_COUNTEREXAMPLE",
    "PROVEN_WITHIN_FINITE_MODEL",
    "BOUNDED_NO_COUNTEREXAMPLE",
    "INCONCLUSIVE_MODEL_GAP",
    "MODEL_STALE_OR_INVALID",
})
PROGRESS_DISPOSITIONS = frozenset({
    "AUTONOMOUSLY_LIVE",
    "FAIRNESS_CONDITIONAL",
    "EXTERNALLY_GATED",
    "INTENTIONAL_WAIT",
    "RECURRING_SERVICE",
    "NO_PROGRESS",
    "UNKNOWN",
})
ADMISSION_RECOMMENDATIONS = frozenset({
    "REPORT_ONLY_PROCEED",
    "REPORT_ONLY_REPAIR",
    "REPORT_ONLY_RECONCILE",
    "REPORT_ONLY_AWAIT_GATE",
    "REPORT_ONLY_NO_RECOMMENDATION",
})
PROPERTY_STATUSES = frozenset({"PASS", "FAIL", "UNKNOWN", "NOT_APPLICABLE"})
```

`finalize_report` computes `report_id = "oar_" + sha256[:24]` and `report_hash` over every report
field except `report_hash` itself. A fixed timestamp produces byte-identical output.

- [ ] **Step 4: Enforce cross-axis anti-inflation invariants**

Constructor validation must refuse:

- `PROVEN_WITHIN_FINITE_MODEL` when `exploration.complete_state_space` is false;
- proof when any property is `UNKNOWN`;
- proof when `known_model_gaps` is non-empty;
- `UNSAFE_COUNTEREXAMPLE` without a counterexample;
- any non-unsafe verdict with a counterexample whose property status is `FAIL`;
- any recommendation not prefixed `REPORT_ONLY_`;
- naive/non-UTC timestamps;
- duplicate property IDs or counterexample IDs.

- [ ] **Step 5: Run report tests and commit**

```bash
pytest -q tests/test_operation_assurance_report.py
git add control_plane/operation_assurance_report.py tests/test_operation_assurance_report.py
git commit -m "feat(ols): add truthful assurance report wire"
```

---

### Task 3: Deterministic transition evaluation and bounded BFS

**Files:**
- Create: `control_plane/operation_assurance_checker.py`
- Create: `tests/test_operation_assurance_checker.py`

**Interfaces:**
- Consumes: all Task 1 model types and Task 2 report types.
- Produces:
  - `OperationAssuranceCheckError(RuntimeError)`
  - internal immutable `ReachabilityGraph`
  - `check_model(model: OperationAssuranceModel, *, generated_at: datetime) -> OperationAssuranceReport`

- [ ] **Step 1: Write deterministic reachability tests**

Create a branch model:

```text
START --a_slow--> MID --finish_mid--> DONE
START --b_fast----------------------> DONE
```

Assert:

- all three states are discovered;
- transition consideration order is `a_slow`, then `b_fast`, then `finish_mid`;
- predecessor reconstruction to `MID` is deterministic;
- two checker runs with the same timestamp are byte-identical.

- [ ] **Step 2: Write bound-honesty tests**

Set `max_states=1` and assert:

```text
complete_state_space = false
limit_reason = STATE_LIMIT_REACHED
assurance_verdict != PROVEN_WITHIN_FINITE_MODEL
```

Set `max_depth=0` and assert the same with `DEPTH_LIMIT_REACHED`.

- [ ] **Step 3: Run and verify RED**

```bash
pytest -q tests/test_operation_assurance_checker.py -k "reachability or limit"
```

Expected: import/API failure.

- [ ] **Step 4: Implement canonical state representation and guard evaluation**

State representation:

```python
State = tuple[str, ...]

def _state_from_mapping(model, values):
    return tuple(values[name] for name in model.variable_order)

def _state_to_mapping(model, state):
    return dict(zip(model.variable_order, state, strict=True))
```

Implement `EQ`, `NEQ`, `IN`, `NOT_IN` without dynamic evaluation. Apply effects simultaneously to a
copied value list. Refuse any transition that somehow produces a value outside its domain even though
the parser already guards that invariant.

- [ ] **Step 5: Implement deterministic BFS**

Use:

```python
queue = collections.deque([(initial_state, 0)])
seen = {initial_state}
parent: dict[State, tuple[State, str] | None] = {initial_state: None}
outgoing: dict[State, tuple[tuple[str, State], ...]] = {}
```

For each state, evaluate transitions sorted by `transition_id`. Add unseen states until the queue
drains or an explicit state/depth limit is reached. A depth limit suppresses expansion beyond the
limit and marks the graph incomplete.

Do not use wall-clock or memory heuristics in OLS-A1.

- [ ] **Step 6: Add transition-scoped safety properties and shortest prefixes**

Support two property forms already parsed in Task 1:

```text
STATE_FORBIDDEN:
  violation_when guards all match the reached state

TRANSITION_FORBIDDEN:
  when guards all match the source state and transition.kind is in forbidden_transition_kinds
```

Check transition violations before applying the forbidden edge. Reconstruct the source-state prefix,
then append one trace step describing the forbidden transition and expected after-state delta without
adding the forbidden state to the accepted reachable graph.

The first failure ordering is:

```text
shortest prefix length
property_id
transition_id
source state fingerprint
```

- [ ] **Step 7: Add the EFFECT_UNKNOWN escape regression**

Fixture semantics:

```text
effect = EFFECT_UNKNOWN
retry_on_alternate.kind = RETRY
safety property NO_EFFECT_UNKNOWN_ESCAPE forbids RETRY and FAILOVER
```

Assert a one-step `UNSAFE_COUNTEREXAMPLE`, recommendation `REPORT_ONLY_REPAIR`, exact property ID,
and no accepted retry successor in the reachable graph.

- [ ] **Step 8: Run focused tests and commit**

```bash
pytest -q tests/test_operation_assurance_checker.py -k "reachability or safety or effect_unknown or limit"
git add control_plane/operation_assurance_checker.py tests/test_operation_assurance_checker.py
git commit -m "feat(ols): add deterministic reachability and safety checks"
```

---

### Task 4: Option-to-complete, proper completion, resources and dead transitions

**Files:**
- Modify: `control_plane/operation_assurance_checker.py`
- Modify: `tests/test_operation_assurance_checker.py`

**Interfaces:**
- Extends `check_model`; no new public API.

- [ ] **Step 1: Write stranded-state option-to-complete test**

Model:

```text
START -> WORK
WORK -> STRANDED
WORK -> DONE
```

`STRANDED` has no gate/wait/recurring classification and no path to a terminal outcome. Assert the
shortest counterexample ends at `STRANDED` with property `OPTION_TO_COMPLETE`.

- [ ] **Step 2: Write terminal-residue tests**

Create terminal models where exactly one defect remains:

- pending `PARENT_CONTINUATION`;
- held non-persistent resource;
- pending `EFFECT_RECONCILIATION`;
- pending `TERMINAL_CLEANUP`.

Each must fail `PROPER_COMPLETION` with the exact unresolved identity. A terminal state with only a
persistent recurring obligation/resource may pass when its recurring outcome explicitly owns it.

- [ ] **Step 3: Write dead-transition tests**

A transition with `required_reachable=true` and impossible guards fails `REQUIRED_TRANSITION_REACHABLE`
only when `complete_state_space=true`. With `max_states=1`, its status is `UNKNOWN`.

- [ ] **Step 4: Run and verify RED**

```bash
pytest -q tests/test_operation_assurance_checker.py -k "option_to_complete or terminal_residue or required_transition"
```

- [ ] **Step 5: Implement reverse completion analysis**

Build the reverse adjacency of the complete or partial reachable graph. Seed accepted good states from
terminal, valid gate/wait, and recurring outcomes. Reverse BFS marks states with an option to reach a
good outcome.

For a state lacking an option, reconstruct the shortest initial prefix using the BFS parent map.
When the graph is incomplete, only emit a `FAIL` for a concrete reached hard dead-end; otherwise
property status is `UNKNOWN`.

- [ ] **Step 6: Implement proper-completion residue checks**

At each terminal outcome, inspect obligations and resources:

```python
pending = obligation.state_variable in obligation.pending_values
released = resource.holder_variable in resource.released_values
```

Non-persistent pending/held items fail. Include sorted IDs in counterexample metadata.

- [ ] **Step 7: Implement required-transition reachability**

Track every transition that is enabled in at least one reached state. Compare against
`required_reachable`. In incomplete graphs, unobserved required transitions are `UNKNOWN`.

- [ ] **Step 8: Run tests and commit**

```bash
pytest -q tests/test_operation_assurance_checker.py -k "option_to_complete or terminal_residue or required_transition"
git add control_plane/operation_assurance_checker.py tests/test_operation_assurance_checker.py
git commit -m "feat(ols): add workflow soundness properties"
```

---

### Task 5: SCC, minimal lasso, recurring progress and weak fairness

**Files:**
- Modify: `control_plane/operation_assurance_checker.py`
- Modify: `tests/test_operation_assurance_checker.py`

**Interfaces:**
- Extends `check_model`.
- Internal helpers:
  - `_strongly_connected_components(graph) -> tuple[tuple[State, ...], ...]`
  - `_shortest_cycle(graph, entry, allowed_states, predicate) -> tuple[tuple[str, State], ...] | None`
  - `_lasso_satisfies_weak_fairness(...) -> bool`

- [ ] **Step 1: Write closed non-progress cycle test**

Model:

```text
START -> A
A --spin_ab--> B
B --spin_ba--> A
```

An obligation remains pending and no transition has an accepted progress tag. Assert:

- `UNSAFE_COUNTEREXAMPLE`;
- property `NO_CLOSED_NON_PROGRESS_SCC`;
- prefix `START -> A`;
- cycle `A -> B -> A`;
- deterministic lasso across reversed source insertion order.

- [ ] **Step 2: Write recurring-service cycle test**

Use the same topology, but each cycle discharges and recreates a persistent
`RECURRING_PROGRESS` epoch and the cycle transition carries `RECURRING_PROGRESS`. Add a matching
recurring outcome. Assert disposition `RECURRING_SERVICE` and no non-progress failure.

- [ ] **Step 3: Write fairness-dependent cycle tests**

Topology:

```text
A --spin--> A
A --finish--> DONE
```

Without fairness, the `spin` lasso can avoid completion and is a liveness witness. With weak fairness
declared for `finish`, the one-state spin lasso is invalid because `finish` is continuously enabled
but absent from the cycle. The report becomes `FAIRNESS_CONDITIONAL` rather than claiming
unconditional autonomous liveness.

Also test that weak fairness does not apply when `finish` is disabled in one cycle state.

- [ ] **Step 4: Run and verify RED**

```bash
pytest -q tests/test_operation_assurance_checker.py -k "non_progress or recurring or weak_fair"
```

- [ ] **Step 5: Implement deterministic Tarjan SCC**

Visit states sorted by fingerprint and outgoing edges sorted by transition ID/target fingerprint.
Sort final SCCs by their minimum state fingerprint. A singleton is cyclic only with a self-loop.

- [ ] **Step 6: Implement closed/non-progress classification**

For each reachable cyclic SCC, compute:

- outgoing edges leaving the SCC;
- accepted terminal/gate/wait/recurring states;
- progress-tagged transitions in the SCC;
- obligations pending through every state.

A `CLOSED_NON_PROGRESS_SCC` has no lawful good outcome, no recurring progress, no outgoing edge, and
preserves at least one non-persistent pending obligation or otherwise makes no accepted progress.

- [ ] **Step 7: Implement deterministic shortest lasso**

Choose the SCC entry with the shortest BFS prefix. For each candidate entry, BFS within the SCC for a
cycle returning to the entry. Select by `(prefix_length, cycle_length, transition_sequence,
entry_fingerprint)`.

Trace output must clearly separate `prefix` and `cycle`.

- [ ] **Step 8: Implement weak-fairness filtering**

For every `WEAK` fairness assumption and each declared transition:

- determine whether the transition is enabled in every cycle state;
- determine whether the transition occurs in the cycle;
- reject the candidate lasso when continuously enabled and absent.

Do not implement or silently emulate strong fairness.

- [ ] **Step 9: Run tests and commit**

```bash
pytest -q tests/test_operation_assurance_checker.py -k "non_progress or recurring or weak_fair"
git add control_plane/operation_assurance_checker.py tests/test_operation_assurance_checker.py
git commit -m "feat(ols): add liveness lassos and weak fairness"
```

---

### Task 6: Starvation, gates/waits and final verdict composition

**Files:**
- Modify: `control_plane/operation_assurance_checker.py`
- Modify: `tests/test_operation_assurance_checker.py`

**Interfaces:**
- Completes `check_model`.

- [ ] **Step 1: Write starvation witness test**

Create two obligations and a cycle that repeatedly services `urgent` while `ordinary` stays pending.
The cycle satisfies all declared weak-fair transition assumptions but never discharges `ordinary`.
Assert `STARVATION_WITNESS` with the pending obligation ID.

- [ ] **Step 2: Write valid external-gate and intentional-wait tests**

An `EXTERNALLY_GATED` state must include:

```text
owner_or_authority
release_condition
return_or_observation_source
wake_or_review_path
time_contract
correction_contract
escalation_or_close_path
source_refs
```

A complete gate yields `progress_disposition=EXTERNALLY_GATED` and
`REPORT_ONLY_AWAIT_GATE`, without claiming autonomous liveness.

A gate missing any field is a load-bearing model gap and yields
`INCONCLUSIVE_MODEL_GAP`.

Repeat for `INTENTIONAL_WAIT`. Add a capacity-parking fixture and a natural-evidence/calendar wait
fixture.

- [ ] **Step 3: Write stale/conflicting source precedence tests**

A source item with `freshness=STALE` or `conflict=CONFLICT` must yield
`MODEL_STALE_OR_INVALID` and `REPORT_ONLY_RECONCILE`, even if the graph otherwise completes.

- [ ] **Step 4: Write final verdict lattice tests**

Cover the full precedence:

```text
stale/conflict
> load-bearing model gap
> concrete counterexample
> complete finite all-pass
> bounded no counterexample
```

A concrete counterexample found before a state limit remains unsafe unless the source itself is stale
or conflicting. A non-load-bearing model gap prevents proof only when its declared semantics can
affect a checked property; otherwise it remains visible as coverage residue and the implementation
must document why it is non-load-bearing.

- [ ] **Step 5: Run and verify RED**

```bash
pytest -q tests/test_operation_assurance_checker.py -k "starvation or external_gate or intentional_wait or stale or verdict"
```

- [ ] **Step 6: Implement gate/wait completeness and disposition**

Validate gate fields in the model parser and compute disposition only from reached matching states.
If more than one disposition applies, use this deterministic precedence:

```text
NO_PROGRESS
EXTERNALLY_GATED
INTENTIONAL_WAIT
RECURRING_SERVICE
FAIRNESS_CONDITIONAL
AUTONOMOUSLY_LIVE
UNKNOWN
```

`NO_PROGRESS` is emitted only with a concrete failed progress property.

- [ ] **Step 7: Implement starvation search**

For each non-persistent obligation that can remain pending in a reachable cyclic SCC, search the
shortest fairness-valid lasso that never reaches a discharged value. Exclude valid gate/wait states
whose contract explicitly owns that obligation.

- [ ] **Step 8: Implement verdict/recommendation precedence**

Use the exact order from Step 4. Every `PropertyResult` must be present and sorted by `property_id`.
Include coverage, assumptions, gaps and exploration receipt in the finalized report.

- [ ] **Step 9: Run checker tests and commit**

```bash
pytest -q tests/test_operation_assurance_checker.py
git add control_plane/operation_assurance_checker.py tests/test_operation_assurance_checker.py
git commit -m "feat(ols): compose truthful operation assurance verdicts"
```

---

### Task 7: Report-only CLI and frozen incident corpus

**Files:**
- Create: `scripts/operation_assurance.py`
- Create: `tests/test_operation_assurance_cli.py`
- Create: `tests/fixtures/operation_assurance/safe_finite.json`
- Create: `tests/fixtures/operation_assurance/watcher_self_deadlock.json`
- Create: `tests/fixtures/operation_assurance/dialogue_carrier_split.json`
- Create: `tests/fixtures/operation_assurance/stranded_parent.json`
- Create: `tests/fixtures/operation_assurance/effect_unknown_failover.json`
- Create: `tests/fixtures/operation_assurance/capacity_valid_wait.json`
- Create: `tests/fixtures/operation_assurance/chairman_external_gate.json`
- Create: `tests/fixtures/operation_assurance/recurring_service.json`
- Create: `tests/fixtures/operation_assurance/weak_fair_starvation.json`
- Create: `tests/fixtures/operation_assurance/stale_projection.json`

**Interfaces:**
- Consumes: `parse_model`, `check_model`, `report_to_dict`.
- Produces:
  - `main(argv: Sequence[str] | None = None, *, stdin=None, stdout=None, stderr=None, generated_at=None) -> int`

- [ ] **Step 1: Write CLI contract tests**

Use direct `main()` injection and subprocess invocation.

Assertions:

- `safe_finite.json` emits valid report JSON and exit 0;
- `effect_unknown_failover.json` emits `UNSAFE_COUNTEREXAMPLE` and exit 0;
- malformed JSON exits 2 with one bounded error line and no traceback;
- malformed model exits 2;
- no CLI option can request admission, mutation, retry, Wake, placement or runtime writes;
- output contains no absolute local path;
- fixed injected `generated_at` yields byte-identical stdout.

- [ ] **Step 2: Run and verify RED**

```bash
pytest -q tests/test_operation_assurance_cli.py
```

- [ ] **Step 3: Implement CLI**

Supported syntax:

```text
python3 scripts/operation_assurance.py MODEL.json
python3 scripts/operation_assurance.py -
```

Options:

```text
--pretty
```

No network/store/runtime flags.

Implementation boundary:

```python
def main(...):
    try:
        raw = stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
        document = json.loads(raw)
        model = parse_model(document)
        report = check_model(model, generated_at=generated_at or datetime.now(UTC))
        json.dump(report_to_dict(report), stdout, sort_keys=True,
                  indent=2 if pretty else None, separators=None if pretty else (",", ":"),
                  ensure_ascii=False, allow_nan=False)
        stdout.write("\n")
        return 0
    except (OSError, json.JSONDecodeError, OperationAssuranceModelError,
            OperationAssuranceCheckError) as exc:
        stderr.write(f"operation assurance refused: {type(exc).__name__}\n")
        return 2
```

Do not forward exception detail that could contain a path or source payload.

- [ ] **Step 4: Add frozen fixtures**

Every hostile fixture must cite its current Mastermind source law or PR identity in
`source_snapshot.sources`. Fixtures model the defect rather than copying Slack prose.

Expected verdicts:

| Fixture | Expected |
|---|---|
| `safe_finite.json` | `PROVEN_WITHIN_FINITE_MODEL` |
| `watcher_self_deadlock.json` | unsafe non-progress/ownerless Sol turn |
| `dialogue_carrier_split.json` | unsafe carrier/return-path property |
| `stranded_parent.json` | unsafe `PARENT_CONTINUATION` |
| `effect_unknown_failover.json` | unsafe transition property |
| `capacity_valid_wait.json` | externally valid intentional wait, no deadlock |
| `chairman_external_gate.json` | external gate, no autonomous claim |
| `recurring_service.json` | recurring-service disposition |
| `weak_fair_starvation.json` | starvation witness |
| `stale_projection.json` | stale/invalid before graph verdict |

- [ ] **Step 5: Run CLI and fixture tests**

```bash
pytest -q tests/test_operation_assurance_cli.py
for f in tests/fixtures/operation_assurance/*.json; do
  python3 scripts/operation_assurance.py "$f" >/tmp/ols-report.json
  python3 -m json.tool /tmp/ols-report.json >/dev/null
done
```

Expected: every fixture yields valid JSON; malformed-input tests alone return 2.

- [ ] **Step 6: Commit**

```bash
git add scripts/operation_assurance.py tests/test_operation_assurance_cli.py tests/fixtures/operation_assurance
git commit -m "feat(ols): add report-only assurance CLI and incident corpus"
```

---

### Task 8: Adversarial mutation fence and exact proof packet

**Files:**
- Modify: `tests/test_operation_assurance_model.py`
- Modify: `tests/test_operation_assurance_report.py`
- Modify: `tests/test_operation_assurance_checker.py`
- Modify: `tests/test_operation_assurance_cli.py`

**Interfaces:**
- No new public API.

- [ ] **Step 1: Add verdict-inflation mutation tests**

Tests must fail under each mutation:

1. change incomplete exploration to proof;
2. treat `known_model_gaps` as empty;
3. treat stale source as fresh;
4. allow unknown guard op;
5. accept retry from `EFFECT_UNKNOWN`;
6. classify a missing-gate contract as valid;
7. ignore terminal residue;
8. ignore one pending parent-continuation obligation;
9. accept first discovered rather than shortest counterexample;
10. omit lasso cycle;
11. infer weak fairness without a declaration;
12. return non-zero for a valid unsafe report and thereby turn CLI into an implicit gate.

Each test includes a comment naming the forbidden mutation it kills.

- [ ] **Step 2: Add deterministic-order property test**

Generate 100 permutations of transition list, state-domain key insertion order, source list and
property list for one fixed model. With fixed `generated_at`, every report must serialize to the same
bytes.

Use `random.Random(0)` only inside the test; production code uses no randomness.

- [ ] **Step 3: Add no-side-effect test**

Monkeypatch:

```python
sqlite3.connect
subprocess.run
subprocess.Popen
socket.socket
urllib.request.urlopen
Path.write_text
Path.write_bytes
```

to raise if called while parsing/checking a fixture. Reading the explicitly supplied model file is
allowed only at the CLI boundary. The core model/checker/report modules perform no filesystem I/O.

- [ ] **Step 4: Run focused and full repository tests**

```bash
pytest -q \
  tests/test_operation_assurance_model.py \
  tests/test_operation_assurance_report.py \
  tests/test_operation_assurance_checker.py \
  tests/test_operation_assurance_cli.py

python3 -m compileall -q \
  control_plane/operation_assurance_model.py \
  control_plane/operation_assurance_report.py \
  control_plane/operation_assurance_checker.py \
  scripts/operation_assurance.py

pytest -q
```

Expected: focused tests and full repository tests pass on the exact head.

- [ ] **Step 5: Verify changed-file boundary**

```bash
git diff --name-only "$(git merge-base HEAD origin/master)"...HEAD
```

Expected paths are only the four OLS-A1 source files and OLS-A1 tests/fixtures listed in this plan.
Any other path requires STOP and Sol reconciliation.

- [ ] **Step 6: Produce continuation handoff**

Return:

```text
operation = OLS-A1 child operation key
pickup_base
head_sha
changed_files
focused_test_receipt
full_repository_test_receipt
hosted_CI_receipt
mutation_falsifiers
fixture verdict table
counterexample minimality evidence
known limitations
current collisions
what merge would and would not make true
```

State explicitly:

```text
Capability after merge: BUILT_NOT_PROVEN / REPORT_ONLY / PRODUCTION_INERT
No live source compiler, Steward/Control Room consumer, admission attachment, runtime conformance,
hard gate, retry, Wake, placement or canary is created.
```

- [ ] **Step 7: Commit final test hardening**

```bash
git add tests/test_operation_assurance_model.py \
        tests/test_operation_assurance_report.py \
        tests/test_operation_assurance_checker.py \
        tests/test_operation_assurance_cli.py
git commit -m "test(ols): harden proof scope and counterexample semantics"
```

## Plan self-review receipt

- **Spec coverage:** closed model, source identity, finite bounds, structural validation, safety,
  option-to-complete, proper completion, dead transitions, SCC/lasso, weak fairness, starvation,
  valid waits/gates, recurring services, stale/correction precedence, orthogonal verdict axes,
  report-only CLI, hostile corpus, deterministic evidence and no-side-effects all map to a task.
- **Deferred by design:** canonical source compiler, Steward/Control Room, admission integration,
  runtime conformance, strong fairness, symbolic/Petri/TLA+/SPIN/Alloy backends, canary and enforcement.
  Each is a later separately reviewed wave.
- **Placeholder scan:** the plan contains no implementation placeholder or unspecified error-handling
  step.
- **Type consistency:** public names consumed by later tasks exactly match Task 1 and Task 2.
- **Stop condition:** OLS-A1 stops at a pure report-only CLI and reviewed fixture corpus. It must not
  absorb OLS-A2 or touch an existing canonical owner.
