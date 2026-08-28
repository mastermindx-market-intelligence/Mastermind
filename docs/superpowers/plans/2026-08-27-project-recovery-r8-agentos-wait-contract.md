# Project Recovery R8-B — Agent OS Typed Wait Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add one minimal typed intentional-wait contract to canonical Macro Agent OS so legitimate long evidence/dependency waits are machine-readable without parsing `next_action` prose or pretending Agent OS claims prove execution.

**Architecture:** Macro remains the sole Agent OS schema/parser owner. Add an optional `wait` object at workstream and wave scope, validate only its closed shape, and project it through existing `agent_os_state.v1` / `context_bundle.v1` read paths. This wave creates no recovery classifier, queue, scheduler, runtime claim, or automatic migration.

**Tech Stack:** Python 3.11+, PyYAML through existing `scripts/agentos.py`, existing Agent OS schemas/CLI, pytest, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-08-27-project-recovery-sentinel-r8-design.md` plus `docs/superpowers/specs/2026-08-27-project-recovery-sentinel-r8-current-state-amendment.md`.

## Global Constraints

- Repository: `mastermindx-market-intelligence/macro` only.
- Planning observation: Macro `main@0758de6b9a7e9e920a6f44e4c1abcd62dbf8074e`; re-pin at pickup.
- Protected Mastermind/Skillpack planning basis: `6f1bc3dd39f1ebecd3c22e44aa11ca7a13fa5182`, Skillpack v1.0.0/bootstrap major 1; re-pin before modification.
- Exact wait kinds: `natural_evidence`, `external_dependency`, `calendar_window`, `external_action`.
- Exact required wait fields: `kind`, `review_after`, `condition`; unknown keys fail validation.
- `review_after` is an ISO date and means mandatory next review, not predicted resolution.
- `condition` is human-readable evidence context only and is never parsed to infer authority/completion.
- No universal stale-age detector.
- Existing Agent OS `claim` remains advisory only.
- No new status enum, lifecycle, queue, scheduler, parser, registry, runtime gate or dispatch behavior.
- Do not edit `WS:PROPHET-CONDITIONAL-FUSION` or any other business workstream merely to demonstrate the schema. Existing legitimate waits receive separate evidence-backed record amendments after this contract is accepted.

## File Structure

- Modify `agentos/schema/workstream.schema.yml` — machine mirror of the optional wait object.
- Modify `research/MASTERMIND_AGENT_OS_STATE_SCHEMA.md` — prose source law for wait semantics and projection.
- Modify `scripts/agentos.py` — validate and serialize the typed wait through existing read paths.
- Create `tests/test_agentos_wait_contract.py` — focused shape/projection falsifiers.
- Modify `tests/test_agentos_compile.py` only if the existing context fixture must assert the additive `wait` field.

---

### Task 1: Freeze the typed wait validation contract

**Files:**
- Create: `tests/test_agentos_wait_contract.py`
- Modify later: `scripts/agentos.py`

**Interfaces:**
- Produces `WAIT_KINDS = {"natural_evidence", "external_dependency", "calendar_window", "external_action"}`.
- Produces `_check_wait(value: Any, *, where: str, path: Path, out: list[Problem]) -> None`.
- A valid wait is exactly `{kind, review_after, condition}`.

- [ ] **Step 1: Write focused RED tests for workstream-level waits**

```python
from pathlib import Path
from scripts import agentos


def _workstream():
    return {
        "key": "TEST-WAIT",
        "title": "Test wait",
        "objective": "Exercise the typed wait contract.",
        "status": "active",
        "program": "test-program",
        "repos": ["macro"],
        "owner": "fable",
        "class": "research",
        "blast_radius": "reversible",
        "ambiguity": "specified",
        "waves": [{"id": "w1", "title": "Accrue", "status": "todo"}],
        "next_action": "Accrue prospectively.",
    }


def _hard(rec):
    return [p for p in agentos.check_workstream(
        rec, Path("agentos/workstreams/WS-TEST-WAIT.md"), {"test-program"}
    ) if p.hard]


def test_workstream_wait_accepts_closed_valid_shape():
    rec = _workstream()
    rec["wait"] = {
        "kind": "natural_evidence",
        "review_after": "2026-09-25",
        "condition": "Review whether the preregistered prospective sample matured.",
    }
    assert _hard(rec) == []


def test_wait_rejects_unknown_kind():
    rec = _workstream()
    rec["wait"] = {
        "kind": "until_ready",
        "review_after": "2026-09-25",
        "condition": "Not a registered kind.",
    }
    assert any(p.rule == "bad-wait" for p in _hard(rec))


def test_wait_requires_review_after_and_condition():
    rec = _workstream()
    rec["wait"] = {"kind": "natural_evidence"}
    hard = _hard(rec)
    assert any("review_after" in p.message for p in hard)
    assert any("condition" in p.message for p in hard)


def test_wait_rejects_unknown_keys_and_relative_dates():
    rec = _workstream()
    rec["wait"] = {
        "kind": "external_action",
        "review_after": "next week",
        "condition": "Operator action is still outstanding.",
        "auto_extend": True,
    }
    hard = _hard(rec)
    assert any("review_after" in p.message for p in hard)
    assert any("auto_extend" in p.message for p in hard)
```

- [ ] **Step 2: Run RED**

Run: `python3 -m pytest tests/test_agentos_wait_contract.py -q`

Expected: at least the invalid-shape tests fail because Agent OS currently ignores `wait`.

- [ ] **Step 3: Add wave-scope symmetry tests**

```python
def test_wave_wait_uses_same_contract():
    rec = _workstream()
    rec["waves"][0]["wait"] = {
        "kind": "calendar_window",
        "review_after": "2026-09-01",
        "condition": "Review at the next declared calendar window.",
    }
    assert _hard(rec) == []


def test_wave_wait_rejects_blank_condition():
    rec = _workstream()
    rec["waves"][0]["wait"] = {
        "kind": "calendar_window",
        "review_after": "2026-09-01",
        "condition": "  ",
    }
    assert any(p.rule == "bad-wait" for p in _hard(rec))
```

- [ ] **Step 4: Commit RED tests**

```bash
git add tests/test_agentos_wait_contract.py
git commit -m "test(agentos): freeze typed intentional-wait contract"
```

---

### Task 2: Implement validation in the canonical Agent OS parser

**Files:**
- Modify: `scripts/agentos.py`
- Test: `tests/test_agentos_wait_contract.py`

**Interfaces:**
- `WAIT_KINDS` exact closed set from Task 1.
- `_check_wait(...)` appends hard `Problem(..., rule="bad-wait", ...)` findings only for malformed authored wait data.
- `_wait_json(value: Any) -> dict[str, str] | None` serializes valid PyYAML date objects to ISO strings for JSON views.

- [ ] **Step 1: Add constants and the closed helper**

Implement near the existing enum/date helpers:

```python
WAIT_KINDS = {
    "natural_evidence", "external_dependency", "calendar_window", "external_action",
}
_WAIT_KEYS = {"kind", "review_after", "condition"}


def _check_wait(value: Any, *, where: str, path: Path, out: list[Problem]) -> None:
    if value is None:
        return
    if not isinstance(value, dict):
        out.append(Problem(path, "bad-wait", f"{where} wait must be a mapping", hard=True))
        return
    unknown = sorted(set(value) - _WAIT_KEYS)
    if unknown:
        out.append(Problem(path, "bad-wait", f"{where} wait has unknown field(s): {', '.join(unknown)}", hard=True))
    kind = value.get("kind")
    if kind not in WAIT_KINDS:
        out.append(Problem(path, "bad-wait", f"{where} wait kind {kind!r} is not registered", hard=True))
    review = value.get("review_after")
    if _as_date(review) is None:
        out.append(Problem(path, "bad-wait", f"{where} wait review_after must be YYYY-MM-DD", hard=True))
    condition = value.get("condition")
    if not isinstance(condition, str) or not condition.strip():
        out.append(Problem(path, "bad-wait", f"{where} wait condition must be a non-empty string", hard=True))


def _wait_json(value: Any) -> dict[str, str] | None:
    if not isinstance(value, dict):
        return None
    review = _as_date(value.get("review_after"))
    if review is None:
        return None
    return {
        "kind": str(value.get("kind")),
        "review_after": review.isoformat(),
        "condition": str(value.get("condition")),
    }
```

- [ ] **Step 2: Call `_check_wait` from `check_workstream`**

Immediately after the normal top-level field checks, call:

```python
_check_wait(rec.get("wait"), where="workstream", path=path, out=out)
```

Inside the existing wave loop, after the wave mapping/id/status validation, call:

```python
_check_wait(wave.get("wait"), where=f"wave[{index}] ({wid})", path=path, out=out)
```

Do not compare `review_after` to today's date in `validate`; expiry is state, not schema validity.

- [ ] **Step 3: Run focused GREEN**

Run: `python3 -m pytest tests/test_agentos_wait_contract.py -q`

Expected: PASS.

- [ ] **Step 4: Run canonical validation regressions**

Run: `python3 scripts/agentos.py validate --quiet`

Expected: exit 0 on current store.

Run: `python3 -m pytest tests/test_agentos_compile.py -q`

Expected: PASS.

- [ ] **Step 5: Commit parser validation**

```bash
git add scripts/agentos.py tests/test_agentos_wait_contract.py
git commit -m "feat(agentos): validate typed intentional waits"
```

---

### Task 3: Project waits through existing Agent OS read contracts

**Files:**
- Modify: `scripts/agentos.py`
- Modify: `tests/test_agentos_wait_contract.py`
- Modify if required by existing fixture shape: `tests/test_agentos_compile.py`

**Interfaces:**
- `agent_os_state.v1` workstream rows may add `wait: object | null`.
- Workstream `waves[]` projections may add `wait: object | null` without renaming existing keys.
- `context_bundle.v1.target` may add `wait: object | null`; scoped wave evidence preserves the exact typed wait when present.

- [ ] **Step 1: Add RED serialization test around `build_state`**

Construct a temporary parsed workstream containing both a top-level wait and a wave wait, invoke the same state-building helper used by `status --dry-run`, and assert:

```python
row = next(r for r in state["workstreams"] if r["key"] == "TEST-WAIT")
assert row["wait"] == {
    "kind": "natural_evidence",
    "review_after": "2026-09-25",
    "condition": "Review whether the preregistered prospective sample matured.",
}
assert row["waves"][0]["wait"]["kind"] == "calendar_window"
```

Use a YAML-decoded `datetime.date(2026, 9, 25)` in one fixture to prove `_wait_json` prevents JSON serialization failures.

- [ ] **Step 2: Run serialization test RED**

Run: `python3 -m pytest tests/test_agentos_wait_contract.py -q`

Expected: FAIL because current state/context projections omit `wait`.

- [ ] **Step 3: Add the additive fields at the existing row builders**

Where `build_state()` constructs each workstream row, add:

```python
"wait": _wait_json(rec.get("wait")),
```

Where wave rows are projected, add:

```python
"wait": _wait_json(wave.get("wait")),
```

Where `compile-context` constructs its exact target/workstream projection, add the same normalized top-level wait and preserve wave waits in the bounded wave block. Do not parse `condition`.

- [ ] **Step 4: Prove JSON and context determinism**

Run twice with identical fixtures and assert byte-identical `json.dumps(..., sort_keys=True)` output.

Run: `python3 -m pytest tests/test_agentos_wait_contract.py tests/test_agentos_compile.py -q`

Expected: PASS.

- [ ] **Step 5: Commit projections**

```bash
git add scripts/agentos.py tests/test_agentos_wait_contract.py tests/test_agentos_compile.py
git commit -m "feat(agentos): expose typed waits in read views"
```

---

### Task 4: Update the Agent OS schema mirrors and freeze the no-authority law

**Files:**
- Modify: `agentos/schema/workstream.schema.yml`
- Modify: `research/MASTERMIND_AGENT_OS_STATE_SCHEMA.md`
- Test: `tests/test_agentos_wait_contract.py`

**Interfaces:**
- Schema mirror documents `wait` at workstream and wave scope.
- Prose law states `review_after` is a review point, not an execution timer and not an automatic renewal.

- [ ] **Step 1: Update machine mirror**

Add under workstream `optional`:

```yaml
  wait:
    type: object
    fields: [kind, review_after, condition]
    note: >
      Typed intentional inactivity only. kind is one of natural_evidence,
      external_dependency, calendar_window, external_action; review_after is the
      mandatory next review date; condition is display-only and never parsed for authority.
```

Add `wait: object` to the wave optional fields with a note that the same contract applies.

- [ ] **Step 2: Update prose schema law**

Document:

```text
wait is optional, exact-scope and non-executing.
A non-expired wait may explain why a future recovery consumer should not call the exact scope abandoned.
An expired wait is still a schema-valid historical fact; consumers surface a missed review gate.
Agent OS never renews, dispatches, wakes or executes because a wait changes state.
```

- [ ] **Step 3: Add a mirror drift assertion**

In `tests/test_agentos_wait_contract.py`, read `agentos/schema/workstream.schema.yml` and assert the four exact kinds and `review_after`/`condition` terms are present so the machine mirror cannot silently omit the parser contract.

- [ ] **Step 4: Run GREEN**

Run: `python3 -m pytest tests/test_agentos_wait_contract.py tests/test_agentos_compile.py -q`

Run: `python3 scripts/agentos.py validate --quiet`

Expected: both pass.

- [ ] **Step 5: Commit docs/schema mirror**

```bash
git add agentos/schema/workstream.schema.yml research/MASTERMIND_AGENT_OS_STATE_SCHEMA.md tests/test_agentos_wait_contract.py
git commit -m "docs(agentos): freeze intentional-wait semantics"
```

---

### Task 5: Current-estate compatibility and migration handoff

**Files:**
- No business workstream modification in this carrier.
- Evidence-only output may be added under `research/project_recovery/` if the repository proof convention requires it.

**Interfaces:**
- Current existing workstreams with no `wait` remain valid and unchanged.
- Emits a bounded candidate list for separate Sol adjudication; it does not author waits from prose.

- [ ] **Step 1: Prove the current store remains valid**

Run:

```bash
python3 scripts/agentos.py validate --quiet
python3 scripts/agentos.py status --dry-run > /tmp/r8_agentos_state.json
python3 scripts/agentos.py compile-context --workstream PROPHET-CONDITIONAL-FUSION --now 2026-08-27T09:00:00Z > /tmp/r8_conditional_fusion_context.json
git status --porcelain
```

Expected: validation succeeds; read commands create no repository changes; existing workstream remains readable with `wait` absent/null.

- [ ] **Step 2: Prove a synthetic legitimate wait survives round-trip**

Use the test fixture only; do not edit the real Conditional Fusion record. Assert its typed wait appears identically in state/context and no automatic expiry/renewal occurs.

- [ ] **Step 3: Produce the migration handoff**

The return to Sol must name current nonterminal scopes that *appear* to require a typed wait based on their accepted source law, but must label every candidate `REQUIRES_SOL_EVIDENCE_REVIEW`. Do not infer a date or condition from prose and do not change the records in this PR.

At minimum include `WS:PROPHET-CONDITIONAL-FUSION` as a candidate because current canonical text explicitly says W3 is prospectively accruing and forbids comparative reads until 20 matured H=10 sessions; the separate record amendment must choose a defensible `review_after` from current evidence rather than this implementation plan.

- [ ] **Step 4: Run hosted CI and stop**

Require the repository's normal hosted semantic/contract gates on the exact PR head. Return exact head SHA, changed files, tests, current-store validation, and migration candidates to Sol.

**Stop condition:** typed wait is parser/schema/view-capable and current-store compatible. Do **not** self-edit business waits, start R8-A, create a recovery finding, schedule anything, or dispatch a worker from Agent OS.
