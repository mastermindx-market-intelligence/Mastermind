# Project Recovery R8-B2 — Agent OS Semantic Program Source Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose Macro’s canonical semantic-program registry through the existing Agent OS read surface so R8 can detect lifecycle=`building` programs with no exact workstream owner without parsing Macro YAML inside Mastermind.

**Architecture:** Reuse `scripts/agentos.py` and its existing PyYAML read of `config/mastermind_programs.yml`. Refactor the current `_load_programs()` join helper into a richer read-only registry projection while preserving `_load_programs()` compatibility, then add one additive nested `program_registry` envelope to `agent_os_state.v1`. No new parser, file, database, scheduler, or authority is created.

**Tech Stack:** Python 3.11+, existing PyYAML dependency in `scripts/agentos.py`, pytest, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-08-27-project-recovery-sentinel-r8-design.md` plus current-state amendment.

## Global Constraints

- Repository: `mastermindx-market-intelligence/macro` only.
- Source registry remains `config/mastermind_programs.yml`; it is architecture/advisory semantic truth, not runtime truth.
- Program/workstream join key is exact `workstream.program == program_registry.programs[].key` only.
- No title/name similarity joins.
- Missing/malformed program registry is explicit unavailable, never an empty healthy registry.
- Existing `validate` behavior and `_load_programs()` callers must remain compatible.
- No new Agent OS status, queue, lifecycle, priority score, recovery finding or dispatch behavior.
- Planning Macro pin `0758de6b9a7e9e920a6f44e4c1abcd62dbf8074e`; re-pin at pickup.

## File Structure

- Modify `scripts/agentos.py` — canonical registry read/projection.
- Modify `research/MASTERMIND_AGENT_OS_STATE_SCHEMA.md` — additive state field contract.
- Create `tests/test_agentos_program_registry.py` — exact-key, availability and determinism tests.

---

### Task 1: Freeze the normalized nested registry envelope

**Files:**
- Create: `tests/test_agentos_program_registry.py`
- Modify later: `scripts/agentos.py`

**Interfaces:**
- `PROGRAM_REGISTRY_SCHEMA = "agentos.program_registry.v1"`.
- `_load_program_registry(path: Path = _PROGRAMS) -> dict[str, Any]`.
- Return shape:

```python
{
    "schema": "agentos.program_registry.v1",
    "available": True,
    "source": "config/mastermind_programs.yml",
    "programs": [
        {
            "key": "cross-repo-contract-governance",
            "name": "Cross-Repository Contract Governance",
            "lifecycle_state": "building",
            "scope": "project",
            "kind": "project_infrastructure",
            "category": "project_infrastructure",
        },
    ],
}
```

Unavailable shape:

```python
{
    "schema": "agentos.program_registry.v1",
    "available": False,
    "reason": "program_registry_unavailable",
    "source": "config/mastermind_programs.yml",
    "programs": [],
}
```

- [ ] **Step 1: Write RED normalization tests**

```python
from pathlib import Path
from scripts import agentos


def test_program_registry_normalizes_exact_keys_and_lifecycle(tmp_path):
    path = tmp_path / "mastermind_programs.yml"
    path.write_text("""
programs:
  beta-program:
    name: Beta
    category: market_intelligence
    kind: intelligence_program
    lifecycle_state: building
    scope: project
  alpha-program:
    name: Alpha
    category: project_infrastructure
    kind: infrastructure
    lifecycle_state: operating
    scope: project
""", encoding="utf-8")
    got = agentos._load_program_registry(path)
    assert got["available"] is True
    assert [p["key"] for p in got["programs"]] == ["alpha-program", "beta-program"]
    assert got["programs"][1]["lifecycle_state"] == "building"


def test_program_registry_unavailable_is_not_healthy_empty(tmp_path):
    got = agentos._load_program_registry(tmp_path / "missing.yml")
    assert got == {
        "schema": "agentos.program_registry.v1",
        "available": False,
        "reason": "program_registry_unavailable",
        "source": "config/mastermind_programs.yml",
        "programs": [],
    }
```

- [ ] **Step 2: Add malformed-row falsifiers**

Require `programs` to be a mapping and each row used by the projection to contain non-empty `name`, registered `lifecycle_state`, `scope`, `kind`, and `category`. A malformed registry returns the same explicit unavailable envelope with `reason="program_registry_malformed"`; it must not silently omit only the bad row.

- [ ] **Step 3: Run RED**

Run: `python3 -m pytest tests/test_agentos_program_registry.py -q`

Expected: FAIL because `_load_program_registry` and schema constant do not exist.

- [ ] **Step 4: Commit RED tests**

```bash
git add tests/test_agentos_program_registry.py
git commit -m "test(agentos): freeze semantic program projection"
```

---

### Task 2: Refactor the existing registry read without breaking validation

**Files:**
- Modify: `scripts/agentos.py`
- Test: `tests/test_agentos_program_registry.py`

**Interfaces:**
- `_load_program_registry(...)` from Task 1.
- `_load_programs() -> set[str] | None` remains available to existing validation code.

- [ ] **Step 1: Add the schema and registered lifecycle set**

Reuse the existing semantic registry vocabulary; do not invent statuses:

```python
PROGRAM_REGISTRY_SCHEMA = "agentos.program_registry.v1"
PROGRAM_LIFECYCLE = {"operating", "building", "planned", "parked", "dormant", "deprecated"}
```

- [ ] **Step 2: Implement `_load_program_registry` using the one existing PyYAML owner**

Read the `programs:` mapping once, fail closed at the envelope level on malformed rows, sort by exact key, and emit only the six bounded fields named in Task 1. Do not copy arbitrary registry prose into the machine envelope.

- [ ] **Step 3: Preserve `_load_programs()` as a compatibility wrapper**

```python
def _load_programs() -> set[str] | None:
    envelope = _load_program_registry(_PROGRAMS)
    if not envelope["available"]:
        return None
    return {row["key"] for row in envelope["programs"]}
```

- [ ] **Step 4: Run focused and existing validation tests**

Run:

```bash
python3 -m pytest tests/test_agentos_program_registry.py tests/test_agentos_compile.py -q
python3 scripts/agentos.py validate --quiet
```

Expected: PASS; current program references continue resolving exactly as before.

- [ ] **Step 5: Commit**

```bash
git add scripts/agentos.py tests/test_agentos_program_registry.py
git commit -m "feat(agentos): expose semantic program registry read"
```

---

### Task 3: Add the registry envelope to `agent_os_state.v1`

**Files:**
- Modify: `scripts/agentos.py`
- Modify: `tests/test_agentos_program_registry.py`
- Modify: `research/MASTERMIND_AGENT_OS_STATE_SCHEMA.md`

**Interfaces:**
- Additive top-level `program_registry` field on `agent_os_state.v1`.
- Existing `workstreams` rows and readiness behavior are untouched.

- [ ] **Step 1: Write RED state projection test**

Use an isolated fixture root or monkeypatch `_PROGRAMS` and assert:

```python
state = agentos.build_state(...)
assert state["schema"] == "agent_os_state.v1"
assert state["program_registry"]["schema"] == "agentos.program_registry.v1"
assert state["program_registry"]["available"] is True
assert any(
    row["key"] == "beta-program" and row["lifecycle_state"] == "building"
    for row in state["program_registry"]["programs"]
)
```

- [ ] **Step 2: Run RED**

Run: `python3 -m pytest tests/test_agentos_program_registry.py -q`

Expected: state lacks `program_registry`.

- [ ] **Step 3: Project the envelope without changing validation semantics**

At state assembly, call `_load_program_registry(_PROGRAMS)` once and attach the returned envelope as `program_registry`. Do not derive program lifecycle from workstream status and do not make an unavailable semantic registry fail `status`.

- [ ] **Step 4: Document the additive state field**

In `research/MASTERMIND_AGENT_OS_STATE_SCHEMA.md`, freeze:

```text
program_registry is a read-only bounded projection of config/mastermind_programs.yml.
It exists for exact semantic joins; it does not make Agent OS the owner of runtime/program execution state.
available=false is semantically distinct from an available registry with zero rows.
```

- [ ] **Step 5: Run GREEN and no-network proof**

Run:

```bash
python3 -m pytest tests/test_agentos_program_registry.py tests/test_agentos_compile.py tests/test_agentos_status.py -q
python3 scripts/agentos.py status --dry-run > /tmp/r8_agentos_programs.json
git status --porcelain
```

Expected: tests pass; read command does not mutate the repository.

- [ ] **Step 6: Commit**

```bash
git add scripts/agentos.py tests/test_agentos_program_registry.py research/MASTERMIND_AGENT_OS_STATE_SCHEMA.md
git commit -m "feat(agentos): project semantic program lifecycle"
```

---

### Task 4: Current-estate exact-join receipt

**Files:**
- Evidence-only optional: `research/project_recovery/R8_B2_PROGRAM_REGISTRY_RECEIPT_2026-08-27.json`

**Interfaces:**
- Machine receipt names exact Macro SHA and exact key sets only.

- [ ] **Step 1: Run state against current Macro main**

Capture exact tested SHA, `program_registry.available`, total program count, lifecycle=`building` program keys, and the exact inverse map from direct workstream `program` fields.

- [ ] **Step 2: Report, do not repair, orphan candidates**

For each `building` program with no exact nonterminal workstream binding, list it as `R8_B2_ORPHAN_CANDIDATE`. This wave does not create a workstream and does not decide `RECOVERY_REQUIRED`; R8-A owns that classification after R1.

- [ ] **Step 3: Require hosted CI and stop**

Return exact PR head, test runs, current-estate receipt and orphan-candidate list to Sol.

**Stop condition:** Macro exposes a deterministic, explicit-availability semantic program envelope through the existing Agent OS state read. Do not start R8-A or create recovery/Linear/Slack state from this PR.
