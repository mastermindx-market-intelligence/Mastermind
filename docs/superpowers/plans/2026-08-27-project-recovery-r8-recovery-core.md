# Project Recovery R8-A — Deterministic Recovery Classifier Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a deterministic, read-only `mastermind.project_recovery_assessment.v1` that turns accepted Session Truth plus canonical Agent OS program/wait observations into exact recovery dispositions and findings without creating another lifecycle or truth store.

**Architecture:** Mastermind owns the pure recovery classifier as a consumer of accepted R1 Session Truth; Macro remains the owner of Agent OS and the semantic program registry. The pure core accepts only explicit normalized documents plus an explicit `as_of` date, performs exact-key joins, and emits an immutable assessment. A thin CLI loads already-produced JSON inputs; it performs no hidden network access and never repairs or dispatches anything.

**Tech Stack:** Python >=3.11, stdlib-only `control_plane` modules, accepted R1 Session Truth interfaces, pytest >=8,<10, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-08-27-project-recovery-sentinel-r8-design.md` plus `docs/superpowers/specs/2026-08-27-project-recovery-sentinel-r8-current-state-amendment.md`.

## Global Constraints

- Repository: `mastermindx-market-intelligence/Mastermind` only.
- Hard dependency: Mastermind PR #170/R1 must be accepted and merged before implementation pickup. At planning time #170 is open/draft at observed head `ec1b9bdd7ec9f1d7ea2fca8a7902a2968d1b6681`; re-pin and consume the merged interfaces, never copy them from the draft branch.
- Hard dependency: R8-B1 exposes typed `wait`; R8-B2 exposes `agentos.program_registry.v1` through `agent_os_state.v1`. If either accepted shape differs from these plans, reconcile this plan before code.
- Protected Skillpack planning basis: `6f1bc3dd39f1ebecd3c22e44aa11ca7a13fa5182`, v1.0.0/bootstrap major 1; re-pin at pickup.
- Pure recovery core has zero network I/O, zero filesystem writes, zero environment reads and zero wall-clock reads.
- Exact joins only: workstream identity, program key, wave id and Session Truth subject/bindings. No fuzzy names/titles.
- No parsing of free-form `next_action`, `condition`, PR title prose or Slack text to invent liveness/gates.
- No universal staleness threshold.
- Runtime unavailable/ambiguous means `UNKNOWN_RECONCILE`, never `RECOVERY_REQUIRED` when runtime truth is necessary to decide safely.
- Slack delivery never proves claim/execution.
- Agent OS `claim` never proves runtime execution.
- Recovery finding/disposition is derived evidence only, not Agent OS status or Executive lifecycle.
- No repair, commission, Linear mutation, Slack mutation, wake, scheduler or worker routing in this wave.

## File Structure

- Create `control_plane/project_recovery_contract.py` — schema constants, strict validation, canonical hashing helpers reused from accepted R1.
- Create `control_plane/project_recovery_rules.py` — pure exact-key indexes and recovery finding/disposition logic.
- Create `control_plane/project_recovery.py` — assessment assembly, semantic projection and human rendering.
- Create `scripts/project_recovery_assessment.py` — thin JSON-in/JSON-out CLI.
- Create `tests/test_project_recovery_contract.py`.
- Create `tests/test_project_recovery_rules.py`.
- Create `tests/test_project_recovery_assessment.py`.
- Create `tests/test_project_recovery_cli.py`.
- Create `tests/fixtures/project_recovery/` with bounded synthetic Session Truth + Agent OS inputs.
- Optional evidence only after current-estate proof: `review_evidence/project_recovery/r8a/`.

---

### Task 1: Freeze the assessment contract and exact input envelope

**Files:**
- Create `control_plane/project_recovery_contract.py`
- Create `tests/test_project_recovery_contract.py`

**Interfaces:**

```python
ASSESSMENT_SCHEMA = "mastermind.project_recovery_assessment.v1"
DISPOSITIONS = {
    "NO_RECOVERY_ACTION",
    "VALID_INTENTIONAL_WAIT",
    "CEO_ATTENTION",
    "RECOVERY_REQUIRED",
    "UNKNOWN_RECONCILE",
}
RECOVERY_CODES = {
    "ORPHAN_BUILDING_PROGRAM",
    "ACTIVE_WITHOUT_CARRIER",
    "UNCLAIMED_COMMISSION",
    "MISSED_REVIEW_GATE",
    "MERGED_PROOF_DEBT",
    "ACTIVE_BUT_COMPLETE",
    "SUPERSEDED_NEXT_ACTION",
    "CEO_DECISION_OVERDUE",
    "RUNTIME_OWNERSHIP_UNKNOWN",
}

class ProjectRecoveryContractError(ValueError): ...

def validate_inputs(
    session_truth: Mapping[str, Any],
    agentos_state: Mapping[str, Any],
    *,
    as_of: str,
) -> tuple[dict[str, Any], dict[str, Any], str]: ...
```

- [ ] **Step 1: Write RED schema/shape tests**

```python
import pytest
from control_plane.project_recovery_contract import (
    ASSESSMENT_SCHEMA, DISPOSITIONS, ProjectRecoveryContractError, validate_inputs,
)


def test_contract_constants_are_closed():
    assert ASSESSMENT_SCHEMA == "mastermind.project_recovery_assessment.v1"
    assert "RECOVERY_REQUIRED" in DISPOSITIONS
    assert "UNKNOWN_RECONCILE" in DISPOSITIONS


def test_inputs_require_accepted_session_truth_schema(session_truth, agentos_state):
    session_truth["schema"] = "not-session-truth"
    with pytest.raises(ProjectRecoveryContractError, match="session_truth"):
        validate_inputs(session_truth, agentos_state, as_of="2026-08-27")


def test_inputs_require_agentos_program_registry(session_truth, agentos_state):
    agentos_state.pop("program_registry")
    with pytest.raises(ProjectRecoveryContractError, match="program_registry"):
        validate_inputs(session_truth, agentos_state, as_of="2026-08-27")


def test_as_of_is_explicit_iso_date(session_truth, agentos_state):
    with pytest.raises(ProjectRecoveryContractError, match="as_of"):
        validate_inputs(session_truth, agentos_state, as_of="today")
```

- [ ] **Step 2: Run RED**

Run: `python -m pytest tests/test_project_recovery_contract.py -q`

Expected: import failure because the module does not exist.

- [ ] **Step 3: Implement strict validation**

Use accepted R1 constants/functions by import, not copied schemas:

```python
from control_plane.session_truth_contract import RECEIPT_SCHEMA, canonical_json, semantic_hash


def _iso_date(value: str) -> str:
    parsed = date.fromisoformat(value)
    if parsed.isoformat() != value:
        raise ProjectRecoveryContractError("as_of must be YYYY-MM-DD")
    return value
```

Validate only the fields R8 requires:

- Session Truth `schema == RECEIPT_SCHEMA`, `findings` list, `observations`/owner evidence per the accepted R1 shape.
- Agent OS `schema == "agent_os_state.v1"`, `workstreams` list, `program_registry.schema == "agentos.program_registry.v1"`, explicit `program_registry.available` boolean.
- exact unique workstream keys and program keys.
- typed `wait` if present must already be the normalized B1 shape; R8 rejects malformed input rather than re-validating YAML semantics.

Do not mutate caller inputs; deep-copy before return.

- [ ] **Step 4: Add duplicate/exact-identity negative tests**

```python
def test_duplicate_workstream_key_fails_closed(session_truth, agentos_state):
    agentos_state["workstreams"].append(dict(agentos_state["workstreams"][0]))
    with pytest.raises(ProjectRecoveryContractError, match="duplicate workstream"):
        validate_inputs(session_truth, agentos_state, as_of="2026-08-27")


def test_unavailable_program_registry_remains_valid_unknown_input(session_truth, agentos_state):
    agentos_state["program_registry"] = {
        "schema": "agentos.program_registry.v1",
        "available": False,
        "reason": "program_registry_unavailable",
        "source": "config/mastermind_programs.yml",
        "programs": [],
    }
    _, state, _ = validate_inputs(session_truth, agentos_state, as_of="2026-08-27")
    assert state["program_registry"]["available"] is False
```

- [ ] **Step 5: Run GREEN and commit**

Run: `python -m pytest tests/test_project_recovery_contract.py -q`

```bash
git add control_plane/project_recovery_contract.py tests/test_project_recovery_contract.py
git commit -m "feat(exec): freeze project recovery assessment contract"
```

---

### Task 2: Build exact indexes and source-owner helpers

**Files:**
- Create `control_plane/project_recovery_rules.py`
- Create `tests/test_project_recovery_rules.py`

**Interfaces:**

```python
def build_recovery_indexes(
    session_truth: Mapping[str, Any],
    agentos_state: Mapping[str, Any],
) -> dict[str, Any]: ...

def session_findings_by_subject(session_truth: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]: ...
```

Index result must include:

```python
{
    "workstreams": {"WS:KEY": row},
    "waves": {("WS:KEY", "wave-id"): wave_row},
    "programs": {"program-key": program_row},
    "workstreams_by_program": {"program-key": ["WS:KEY", ...]},
    "session_findings": {"WS:KEY": [finding, ...]},
}
```

- [ ] **Step 1: Write RED exact-key tests**

```python
def test_program_inverse_map_is_exact(session_truth, agentos_state):
    idx = build_recovery_indexes(session_truth, agentos_state)
    assert idx["workstreams_by_program"]["alpha-program"] == ["WS:ALPHA"]
    assert "WS:ALPHA-V2" not in idx["workstreams_by_program"]["alpha-program"]


def test_similar_titles_do_not_join(session_truth, agentos_state):
    agentos_state["program_registry"]["programs"].append({
        "key": "alpha-program-v2", "name": "Alpha Program", "lifecycle_state": "building",
        "scope": "project", "kind": "intelligence_program", "category": "market_intelligence",
    })
    idx = build_recovery_indexes(session_truth, agentos_state)
    assert idx["workstreams_by_program"].get("alpha-program-v2", []) == []
```

- [ ] **Step 2: Freeze accepted Session Truth finding consumption**

Do not hard-code draft R1 shape before merge. At pickup, read the merged `session_truth_rules.py` finding subject contract and write tests against the accepted field. The implementation must index Session Truth findings only by exact accepted subject identity. If R1 does not expose exact workstream/program subject identities needed by R8, stop and return to Sol for a bounded R1-compatible extension rather than NLP parsing details.

Required consumed finding families when present:

```text
MULTIPLE_ACTIVE_CARRIERS
GITHUB_MERGE_WITH_PROOF_OPEN
SUPERSEDED_NEXT_ACTION
RUNTIME_STATE_UNAVAILABLE
RUNTIME_STATE_STALE
SLACK_TRANSPORT_WITHOUT_RECEIVER
SLACK_TRANSPORT_WITHOUT_ACK
CEO_SEAT_USED_AS_WORKER
FALSE_LINEAR_COMPLETION
```

- [ ] **Step 3: Run RED**

Run: `python -m pytest tests/test_project_recovery_rules.py -q`

Expected: import/function failure.

- [ ] **Step 4: Implement deterministic indexes only**

Sort every multi-value index by exact key/id. Do not classify recovery yet. Missing `program_registry.available` yields empty program index plus an explicit `program_registry_available=False` marker; it must not look like “zero programs”.

- [ ] **Step 5: Run GREEN and commit**

Run: `python -m pytest tests/test_project_recovery_rules.py -q`

```bash
git add control_plane/project_recovery_rules.py tests/test_project_recovery_rules.py
git commit -m "feat(exec): index exact recovery evidence"
```

---

### Task 3: Implement typed wait and CEO-gate classification

**Files:**
- Modify `control_plane/project_recovery_rules.py`
- Modify `tests/test_project_recovery_rules.py`

**Interfaces:**

```python
def wait_state(wait: Mapping[str, Any] | None, *, as_of: str) -> str:
    # NONE | VALID | EXPIRED

def classify_scope_gate(
    workstream: Mapping[str, Any],
    wave: Mapping[str, Any] | None,
    *,
    as_of: str,
) -> list[dict[str, Any]]: ...
```

- [ ] **Step 1: Write RED legitimate-wait tests**

```python
def test_nonexpired_wait_is_valid_not_recovery():
    assert wait_state({
        "kind": "natural_evidence",
        "review_after": "2026-09-25",
        "condition": "Prospective sample review.",
    }, as_of="2026-08-27") == "VALID"


def test_expired_wait_is_missed_review_gate():
    assert wait_state({
        "kind": "calendar_window",
        "review_after": "2026-08-20",
        "condition": "Review after the declared window.",
    }, as_of="2026-08-27") == "EXPIRED"
```

- [ ] **Step 2: Write CEO-decision overdue test**

```python
def test_needs_ceo_by_when_becomes_attention_not_worker_dispatch(base_workstream):
    base_workstream["needs_ceo"] = {
        "question": "Choose authority boundary",
        "options": ["A", "B"],
        "recommendation": "A",
        "by_when": "2026-08-26",
    }
    findings = classify_scope_gate(base_workstream, None, as_of="2026-08-27")
    assert {f["code"] for f in findings} == {"CEO_DECISION_OVERDUE"}
    assert findings[0]["disposition"] == "CEO_ATTENTION"
```

- [ ] **Step 3: Implement date-only comparison**

Use `date.fromisoformat` on already-normalized values. Never read `datetime.now()`.

Rules:

- valid wait on exact unfinished scope contributes `VALID_INTENTIONAL_WAIT` disposition if no fatal/blocking Session Truth collision applies.
- expired wait emits `MISSED_REVIEW_GATE`/`CEO_ATTENTION`; it never auto-renews.
- overdue `needs_ceo.by_when` emits `CEO_DECISION_OVERDUE`/`CEO_ATTENTION`.
- `condition`, `question`, `recommendation` are copied only as bounded display context; they are never parsed for machine authority.

- [ ] **Step 4: Run GREEN and commit**

Run: `python -m pytest tests/test_project_recovery_rules.py -q`

```bash
git add control_plane/project_recovery_rules.py tests/test_project_recovery_rules.py
git commit -m "feat(exec): classify typed recovery waits and gates"
```

---

### Task 4: Implement orphan, carrier, proof-debt and runtime-unknown findings

**Files:**
- Modify `control_plane/project_recovery_rules.py`
- Modify `tests/test_project_recovery_rules.py`

**Interfaces:**

```python
def detect_recovery_findings(
    session_truth: Mapping[str, Any],
    agentos_state: Mapping[str, Any],
    *,
    as_of: str,
) -> list[dict[str, Any]]: ...
```

Each finding must contain at least:

```python
{
    "code": str,
    "subject": str,
    "program": str | None,
    "workstream": str | None,
    "wave": str | None,
    "disposition": str,
    "canonical_owner": str,
    "evidence": list[dict[str, Any]],
    "next_ceo_action": str,
}
```

- [ ] **Step 1: Write `ORPHAN_BUILDING_PROGRAM` RED test**

```python
def test_building_program_without_nonterminal_workstream_is_orphan(session_truth, agentos_state):
    agentos_state["program_registry"]["programs"] = [{
        "key": "orphan-program", "name": "Orphan", "lifecycle_state": "building",
        "scope": "project", "kind": "research_program", "category": "market_intelligence",
    }]
    agentos_state["workstreams"] = []
    findings = detect_recovery_findings(session_truth, agentos_state, as_of="2026-08-27")
    row = next(f for f in findings if f["code"] == "ORPHAN_BUILDING_PROGRAM")
    assert row["subject"] == "PROGRAM:orphan-program"
    assert row["disposition"] == "RECOVERY_REQUIRED"
```

If `program_registry.available=False`, the same input must produce no orphan assertion; assessment later carries `UNKNOWN_RECONCILE` for registry coverage.

- [ ] **Step 2: Write active-carrier and runtime-unknown paired tests**

```python
def test_active_exact_carrier_suppresses_active_without_carrier(active_case):
    active_case.session_truth["findings"] = []
    # use accepted R1 GitHub observation/binding shape for one exact active carrier
    findings = detect_recovery_findings(active_case.session_truth, active_case.agentos, as_of="2026-08-27")
    assert "ACTIVE_WITHOUT_CARRIER" not in {f["code"] for f in findings}


def test_runtime_unavailable_yields_unknown_not_duplicate_recovery(active_quiet_case):
    active_quiet_case.session_truth["findings"].append(r1_finding("RUNTIME_STATE_UNAVAILABLE", "WS:QUIET"))
    findings = detect_recovery_findings(active_quiet_case.session_truth, active_quiet_case.agentos, as_of="2026-08-27")
    row = next(f for f in findings if f["code"] == "RUNTIME_OWNERSHIP_UNKNOWN")
    assert row["disposition"] == "UNKNOWN_RECONCILE"
    assert not any(f["code"] == "ACTIVE_WITHOUT_CARRIER" and f["disposition"] == "RECOVERY_REQUIRED" for f in findings)
```

- [ ] **Step 3: Write Session Truth-derived proof/transport tests**

Map accepted R1 findings without re-deriving them:

- `GITHUB_MERGE_WITH_PROOF_OPEN` -> `MERGED_PROOF_DEBT`.
- `SUPERSEDED_NEXT_ACTION` -> same R8 code, organizational repair/CEO attention.
- `SLACK_TRANSPORT_WITHOUT_RECEIVER` or accepted equivalent -> `UNCLAIMED_COMMISSION` only when durable organizational evidence says a commission remains owed.
- `MULTIPLE_ACTIVE_CARRIERS` -> `UNKNOWN_RECONCILE`/blocking; no new recovery commission.

Test Slack text alone never mints `UNCLAIMED_COMMISSION` if R1 did not establish the typed transport/receiver disagreement.

- [ ] **Step 4: Implement `ACTIVE_BUT_COMPLETE` without prose**

If a top-level workstream status is nonterminal but every authored wave is `done|dropped`, emit `ACTIVE_BUT_COMPLETE`/`CEO_ATTENTION` with next action “repair Agent OS organizational status; do not create new build”. Do not infer hidden obligations from prose.

- [ ] **Step 5: Run GREEN and commit**

Run: `python -m pytest tests/test_project_recovery_rules.py -q`

```bash
git add control_plane/project_recovery_rules.py tests/test_project_recovery_rules.py
git commit -m "feat(exec): detect abandoned and uncertain program frontiers"
```

---

### Task 5: Assemble the immutable assessment and stable semantic hash

**Files:**
- Create `control_plane/project_recovery.py`
- Create `tests/test_project_recovery_assessment.py`

**Interfaces:**

```python
def assess_recovery(
    session_truth: Mapping[str, Any],
    agentos_state: Mapping[str, Any],
    *,
    as_of: str,
    observed_at: str,
) -> dict[str, Any]: ...

def semantic_projection(assessment: Mapping[str, Any]) -> dict[str, Any]: ...

def render_assessment(assessment: Mapping[str, Any]) -> str: ...
```

- [ ] **Step 1: Write RED deterministic assessment test**

```python
def test_same_inputs_same_semantic_hash(session_truth, agentos_state):
    one = assess_recovery(session_truth, agentos_state, as_of="2026-08-27", observed_at="2026-08-27T09:00:00Z")
    two = assess_recovery(session_truth, agentos_state, as_of="2026-08-27", observed_at="2026-08-27T09:05:00Z")
    assert one["semantic_hash"] == two["semantic_hash"]
    assert semantic_projection(one) == semantic_projection(two)
    assert one["observed_at"] != two["observed_at"]
```

- [ ] **Step 2: Freeze summary counts**

Assessment must include:

```python
"summary": {
    "NO_RECOVERY_ACTION": int,
    "VALID_INTENTIONAL_WAIT": int,
    "CEO_ATTENTION": int,
    "RECOVERY_REQUIRED": int,
    "UNKNOWN_RECONCILE": int,
}
```

Counts are per assessed subject after deterministic precedence, not raw finding count.

Precedence:

```text
UNKNOWN_RECONCILE (fatal/blocking uncertainty/collision)
> RECOVERY_REQUIRED
> CEO_ATTENTION
> VALID_INTENTIONAL_WAIT
> NO_RECOVERY_ACTION
```

A blocking duplicate-carrier/runtime-unknown subject cannot simultaneously be advertised as safe `RECOVERY_REQUIRED`.

- [ ] **Step 3: Implement assembly using accepted R1 canonical hash helper**

Envelope fields:

```python
{
    "schema": ASSESSMENT_SCHEMA,
    "as_of": "2026-08-27",
    "observed_at": "...Z",
    "sources": {
        "session_truth_semantic_hash": session_truth["semantic_hash"],
        "agentos_source_sha": ...,
        "program_registry_available": bool,
    },
    "summary": {...},
    "subjects": [...],
    "findings": [...],
    "semantic_hash": "sha256:...",
}
```

The semantic projection excludes `observed_at` but includes `as_of` because wait expiry semantics depend on it.

- [ ] **Step 4: Add render test**

Human render must name each `RECOVERY_REQUIRED`/`UNKNOWN_RECONCILE` subject, finding code and next CEO action. It must not print raw Slack bodies, credentials or arbitrary source prose.

- [ ] **Step 5: Run GREEN and commit**

Run: `python -m pytest tests/test_project_recovery_assessment.py tests/test_project_recovery_rules.py tests/test_project_recovery_contract.py -q`

```bash
git add control_plane/project_recovery.py tests/test_project_recovery_assessment.py
git commit -m "feat(exec): assemble deterministic project recovery assessment"
```

---

### Task 6: Add a zero-network CLI over explicit normalized inputs

**Files:**
- Create `scripts/project_recovery_assessment.py`
- Create `tests/test_project_recovery_cli.py`
- Create bounded fixtures under `tests/fixtures/project_recovery/`

**Interfaces:**

```text
python3 scripts/project_recovery_assessment.py \
  --session-truth /path/session_truth.json \
  --agentos-state /path/agent_os_state.json \
  --as-of 2026-08-27 \
  --observed-at 2026-08-27T09:00:00Z \
  --json
```

- [ ] **Step 1: Write RED CLI test**

Invoke in a temp directory with socket calls monkeypatched/blocked. Assert exit 0, exact schema, no files created, and no source input changed.

- [ ] **Step 2: Implement argparse + JSON loading only**

No GitHub/Linear/Slack/Executive acquisition in this CLI. Missing or malformed input exits nonzero with a concise contract error; it never substitutes empty state.

- [ ] **Step 3: Add `--text` render mode and mutual exclusion test**

Require exactly one of `--json` or `--text`.

- [ ] **Step 4: Run GREEN**

Run: `python -m pytest tests/test_project_recovery_cli.py -q`

- [ ] **Step 5: Commit**

```bash
git add scripts/project_recovery_assessment.py tests/test_project_recovery_cli.py tests/fixtures/project_recovery
git commit -m "feat(exec): add read-only project recovery CLI"
```

---

### Task 7: Adversarial fixture matrix and current-estate read-only census

**Files:**
- Modify tests under `tests/fixtures/project_recovery/` and recovery test modules.
- Optional sanitized evidence under `review_evidence/project_recovery/r8a/`.

**Interfaces:**
- No new code interface; acceptance evidence only.

- [ ] **Step 1: Encode all twelve approved falsifiers**

Fixtures/tests must discriminate:

1. abandoned Stock-Identity-shaped case -> `RECOVERY_REQUIRED`;
2. expired natural review -> `MISSED_REVIEW_GATE`;
3. valid prospective wait -> `VALID_INTENTIONAL_WAIT`;
4. exact current carrier -> `NO_RECOVERY_ACTION`;
5. Slack dead-letter + no receiver -> `UNCLAIMED_COMMISSION` only from typed R1 finding;
6. merged-but-proof-open -> `MERGED_PROOF_DEBT`;
7. runtime unavailable -> `UNKNOWN_RECONCILE`;
8. building program no workstream -> `ORPHAN_BUILDING_PROGRAM`;
9. all waves terminal/top active -> `ACTIVE_BUT_COMPLETE`;
10. duplicate carrier -> blocking `UNKNOWN_RECONCILE`;
11. Linear false-green cannot erase proof debt;
12. stale `next_action` -> consume R1 `SUPERSEDED_NEXT_ACTION`, no NLP inference.

- [ ] **Step 2: Run the full recovery suite twice**

Run:

```bash
python -m pytest tests/test_project_recovery_contract.py tests/test_project_recovery_rules.py tests/test_project_recovery_assessment.py tests/test_project_recovery_cli.py -q
python -m pytest tests/test_project_recovery_contract.py tests/test_project_recovery_rules.py tests/test_project_recovery_assessment.py tests/test_project_recovery_cli.py -q
```

Expected: identical pass counts; deterministic fixture semantic hashes.

- [ ] **Step 3: Produce current-estate inputs through accepted owners**

Use the merged R1 acquisition/snapshot/receipt path and current Macro Agent OS `status --dry-run` with B1/B2 accepted. Do not hand-edit an input to make a desired recovery finding appear. Persist only sanitized normalized observations/assessment if current evidence policy allows it.

- [ ] **Step 4: Run one real current portfolio census**

Record:

- exact protected Mastermind Skillpack SHA;
- exact Mastermind and Macro source SHAs;
- Session Truth semantic hash;
- assessed subject count;
- summary disposition counts;
- every `RECOVERY_REQUIRED`, `CEO_ATTENTION`, `UNKNOWN_RECONCILE` subject/finding code;
- known false-positive/negative review against the approved examples.

This is read-only. Do not repair the findings in the R8-A carrier.

- [ ] **Step 5: Require hosted CI and Sol review**

Run the repository's exact-head hosted CI and return immutable head, changed files, current-estate receipt and any classification ambiguity to Sol.

**Stop condition:** the deterministic assessment is `BUILT_NOT_PROVEN` until Sol accepts the current-estate census. It does not become `PROVEN_LIVE` until later R8-G proves a genuinely fresh Sol can consume it in the real operating path.
