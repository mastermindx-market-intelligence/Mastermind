# Project Recovery R8-C — Improvement Agenda Ingestion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Feed accepted Project Recovery assessments into Mastermind’s existing Improvement Agenda so ignored/dead projects become ranked `ceo-sol` work without creating a second priority engine, scheduler or execution path.

**Architecture:** `brain/improvement_agenda.py` remains the only ranker. Add one typed `project-recovery` source that converts an already-deterministic `mastermind.project_recovery_assessment.v1` into normal Agenda items before the existing rank/age/readiness stages. On-demand callers may inject an assessment directly; weekly automation may use a read-only current-assessment provider only after R8-A and the accepted R1 acquisition path can build current inputs without inventing a parallel GitHub/Linear/Slack reader.

**Tech Stack:** Python >=3.11, existing Mastermind Agenda module and scheduler, R8-A recovery assessment, pytest.

**Spec:** `docs/superpowers/specs/2026-08-27-project-recovery-sentinel-r8-design.md` plus current-state amendment.

## Global Constraints

- Repository: `mastermindx-market-intelligence/Mastermind` only.
- Hard dependency: R8-A current recovery assessment contract accepted.
- Improvement Agenda implementation is `brain/improvement_agenda.py`; this corrects the historical “Macro Improvement Agenda” wording in the approved design.
- Existing Agenda remains the sole ranker and sole `data/agenda/**` writer.
- Existing `improvement_agenda_weekly` schedule in `app/scheduler.py` remains the only scheduled Agenda job; no new cron/daemon/jobstore entry.
- Recovery input is derived evidence; Agenda must not recalculate Session Truth or Agent OS liveness.
- No recovery item may execute, dispatch, wake, mutate a seat, create a Linear issue or post Slack.
- `UNKNOWN_RECONCILE` stays visible but never becomes a runnable worker instruction.
- Missing/unavailable current recovery input must be explicit in Agenda metadata and must not erase unrelated Agenda sources.
- Do not parse recovery `next_ceo_action` as machine authority; it is display guidance from the deterministic R8-A assessment.

## File Structure

- Modify `brain/improvement_agenda.py` — recovery source, class/owner vocabulary and injectable/current provider seam.
- Modify `tests/test_improvement_agenda.py` — ranking, fail-open, dedup and no-execution tests.
- Create `control_plane/project_recovery_current.py` only if accepted R1 exposes all read paths needed to build a current assessment without duplicating acquisition. If not, stop weekly provider wiring and keep the supported direct-injection/on-demand path.
- Create `tests/test_project_recovery_current.py` only if that provider is built.
- Modify `app/scheduler.py` only if the accepted current provider can be called safely from the existing Agenda job; no new schedule entry.

---

### Task 1: Freeze Agenda vocabulary and assessment-to-item conversion

**Files:**
- Modify `tests/test_improvement_agenda.py`
- Modify later `brain/improvement_agenda.py`

**Interfaces:**

```python
CLASS_RECOVERY = "project-recovery"
OWNER_SOL = "ceo-sol"

def _from_project_recovery(assessment: Mapping[str, Any] | None) -> list[dict]: ...
```

Stable item id:

```text
project-recovery:<subject>:<finding-code>
```

- [ ] **Step 1: Write RED conversion tests**

```python
from brain import improvement_agenda as agenda


def test_recovery_required_becomes_ceo_sol_item(recovery_assessment):
    rows = agenda._from_project_recovery(recovery_assessment(
        subject="WS:STOCK-IDENTITY",
        code="ACTIVE_WITHOUT_CARRIER",
        disposition="RECOVERY_REQUIRED",
    ))
    assert len(rows) == 1
    row = rows[0]
    assert row["id"] == "project-recovery:WS:STOCK-IDENTITY:ACTIVE_WITHOUT_CARRIER"
    assert row["class"] == "project-recovery"
    assert row["owner"] == "ceo-sol"
    assert row["agentos_ref"] == {"workstream": "WS:STOCK-IDENTITY", "wave": None}
    assert row["evidence"]


def test_unknown_reconcile_is_visible_but_not_worker_owned(recovery_assessment):
    rows = agenda._from_project_recovery(recovery_assessment(
        subject="WS:QUIET",
        code="RUNTIME_OWNERSHIP_UNKNOWN",
        disposition="UNKNOWN_RECONCILE",
    ))
    assert rows[0]["owner"] == "ceo-sol"
    assert "reconcile" in rows[0]["suggested_fix"].lower()
```

- [ ] **Step 2: Write no-item cases**

`NO_RECOVERY_ACTION` and `VALID_INTENTIONAL_WAIT` subjects do not become corrective Agenda items by default. A valid wait remains visible through the recovery assessment/Control Room but does not crowd the ranked fix list until it expires.

```python
def test_healthy_and_valid_wait_subjects_do_not_create_fix_items(mixed_assessment):
    ids = {row["id"] for row in agenda._from_project_recovery(mixed_assessment)}
    assert not any("NO_RECOVERY_ACTION" in value for value in ids)
    assert not any("VALID_INTENTIONAL_WAIT" in value for value in ids)
```

- [ ] **Step 3: Run RED**

Run: `python -m pytest tests/test_improvement_agenda.py -q`

Expected: recovery constants/function do not exist.

- [ ] **Step 4: Commit RED tests**

```bash
git add tests/test_improvement_agenda.py
git commit -m "test(agenda): freeze project recovery ingestion"
```

---

### Task 2: Implement the recovery source with deterministic severity mapping

**Files:**
- Modify `brain/improvement_agenda.py`
- Modify `tests/test_improvement_agenda.py`

**Interfaces:**
- `_from_project_recovery(...)` validates only `mastermind.project_recovery_assessment.v1` and fails open to `[]` on unavailable/malformed optional input.
- Recovery source does not re-score/reclassify the underlying finding; it maps disposition to the existing numeric ranking framework.

Recommended rank base:

```python
CLASS_RECOVERY = "project-recovery"
_CLASS_WEIGHT[CLASS_RECOVERY] = 92
OWNER_SOL = "ceo-sol"
```

Recommended severity bump by disposition:

```python
_RECOVERY_SEVERITY = {
    "RECOVERY_REQUIRED": 1.0,
    "CEO_ATTENTION": 0.8,
    "UNKNOWN_RECONCILE": 0.7,
}
```

The Agenda rank remains the only rank: R8-A does not emit a numeric priority score.

- [ ] **Step 1: Add constants and closed assessment validation**

```python
def _from_project_recovery(assessment: Mapping[str, Any] | None) -> list[dict]:
    if not isinstance(assessment, Mapping):
        return []
    if assessment.get("schema") != "mastermind.project_recovery_assessment.v1":
        return []
    findings = assessment.get("findings")
    if not isinstance(findings, list):
        return []
    ...
```

- [ ] **Step 2: Convert only actionable/attention findings**

For each finding with disposition in `RECOVERY_REQUIRED|CEO_ATTENTION|UNKNOWN_RECONCILE`, require non-empty `code`, `subject`, `evidence`, `next_ceo_action`. Construct with existing `_item(...)`:

```python
agentos_ref = None
ws = finding.get("workstream")
wave = finding.get("wave")
if isinstance(ws, str) and ws.startswith("WS:"):
    agentos_ref = {"workstream": ws, "wave": wave if isinstance(wave, str) else None}

row = _item(
    f"project-recovery:{subject}:{code}",
    CLASS_RECOVERY,
    f"{subject} requires CEO recovery review ({code})",
    evidence=[_bounded_evidence_string(e) for e in finding["evidence"]],
    suggested_fix=str(finding["next_ceo_action"]),
    fix_type=FIX_CODE,
    expected_impact="Restore an explicit lawful frontier or close the stale organizational state.",
    owner=OWNER_SOL,
    severity=_RECOVERY_SEVERITY[disposition],
    agentos_ref=agentos_ref,
    extra={
        "recovery_code": code,
        "recovery_disposition": disposition,
        "recovery_subject": subject,
        "assessment_semantic_hash": assessment.get("semantic_hash"),
    },
)
```

Evidence renderer must use only bounded normalized fields (owner/source/hash/reason code), never raw Slack body or arbitrary retrieved prose.

- [ ] **Step 3: Run focused GREEN**

Run: `python -m pytest tests/test_improvement_agenda.py -q`

- [ ] **Step 4: Commit**

```bash
git add brain/improvement_agenda.py tests/test_improvement_agenda.py
git commit -m "feat(agenda): rank CEO project recovery findings"
```

---

### Task 3: Inject recovery into `build()` before the existing rank/age stage

**Files:**
- Modify `brain/improvement_agenda.py`
- Modify `tests/test_improvement_agenda.py`

**Interfaces:**

Change public build signature additively:

```python
def build(
    asof: date | None = None,
    *,
    cio_rep: dict | None = None,
    recovery_assessment: Mapping[str, Any] | None = None,
) -> dict:
```

Existing callers remain valid.

- [ ] **Step 1: Write RED ranking integration test**

```python
def test_build_ranks_recovery_with_existing_items(monkeypatch, recovery_assessment):
    # monkeypatch unrelated sources to deterministic fixture rows
    result = agenda.build(
        date(2026, 8, 27),
        cio_rep={"per_seat": []},
        recovery_assessment=recovery_assessment(
            subject="WS:STOCK-IDENTITY",
            code="ACTIVE_WITHOUT_CARRIER",
            disposition="RECOVERY_REQUIRED",
        ),
    )
    item = next(row for row in result["items"] if row["class"] == "project-recovery")
    assert item["owner"] == "ceo-sol"
    assert item["rank_score"] >= 92
```

- [ ] **Step 2: Insert source before P3/ranking**

After existing accountability source collection and before `items = [it for it in items if it.get("evidence")]`, call:

```python
try:
    items.extend(_from_project_recovery(recovery_assessment) or [])
except Exception:
    pass
```

Do not annotate the recovery source after rank; it must participate in the one existing rank/age calculation like every other Agenda item.

- [ ] **Step 3: Preserve Agent OS readiness annotation order**

The existing post-rank readiness annotation remains unchanged. Recovery rows with an exact `agentos_ref` receive current readiness annotation after ranking; orphan `PROGRAM:` rows legitimately have no workstream ref and get `not_applicable` readiness.

- [ ] **Step 4: Add stable age/dedup regression**

Build two consecutive week artifacts with the same recovery item id and prove the existing age carry-forward logic increments age rather than producing a fresh duplicate.

- [ ] **Step 5: Run GREEN and commit**

Run: `python -m pytest tests/test_improvement_agenda.py -q`

```bash
git add brain/improvement_agenda.py tests/test_improvement_agenda.py
git commit -m "feat(agenda): fuse project recovery into sole priority ranker"
```

---

### Task 4: Add an explicit recovery-input receipt to Agenda output

**Files:**
- Modify `brain/improvement_agenda.py`
- Modify `tests/test_improvement_agenda.py`

**Interfaces:**

Agenda output gets one additive source receipt:

```python
"recovery_input": {
    "available": bool,
    "schema": "mastermind.project_recovery_assessment.v1" | None,
    "semantic_hash": str | None,
    "as_of": str | None,
    "degraded": list[str],
}
```

- [ ] **Step 1: Write RED missing-input test**

```python
def test_missing_recovery_input_is_explicit_not_healthy_empty(monkeypatch):
    result = agenda.build(date(2026, 8, 27), cio_rep={"per_seat": []})
    assert result["recovery_input"]["available"] is False
    assert result["recovery_input"]["degraded"] == ["recovery_assessment_unavailable"]
```

- [ ] **Step 2: Write available-input test**

Assert schema/hash/as_of are copied from the assessment and no full source document is duplicated into the Agenda artifact.

- [ ] **Step 3: Implement additive receipt**

Do not make `recovery_input.available=False` fail the Agenda. It is an observability fact only; other Agenda sources and their ranking remain intact.

- [ ] **Step 4: Run GREEN and commit**

Run: `python -m pytest tests/test_improvement_agenda.py -q`

```bash
git add brain/improvement_agenda.py tests/test_improvement_agenda.py
git commit -m "feat(agenda): expose recovery input health"
```

---

### Task 5: Determine whether a current-assessment provider is legally buildable

**Files:**
- Inspect accepted R1 modules after merge.
- Create `control_plane/project_recovery_current.py` and `tests/test_project_recovery_current.py` only if every required source has an accepted read-only acquisition path.

**Interfaces if buildable:**

```python
class CurrentRecoveryUnavailable(RuntimeError): ...

def build_current_assessment(
    *,
    as_of: str,
    observed_at: str,
    protected_sha: str,
    macro_root: str | None = None,
    snapshots: Mapping[str, Path] | None = None,
) -> dict[str, Any]: ...
```

This provider may orchestrate accepted R1 acquisition/normalization and R8-A `assess_recovery`; it may not implement new GitHub/Linear/Slack/Executive readers.

- [ ] **Step 1: Audit merged R1 acquisition ownership**

Answer exactly:

```text
Can current code obtain:
- protected Skillpack: yes/no
- Agent OS state: yes/no
- GitHub normalized observation: yes/no and exact provider
- Linear normalized observation: yes/no and exact provider
- Slack normalized observation: yes/no and exact provider
- Executive normalized observation: yes/no and exact provider
```

R1 may intentionally accept external JSON snapshots instead of fetching apps. That is valid; it means an autonomous weekly current provider is **not yet available**.

- [ ] **Step 2A: If every required current provider exists, write RED provider tests**

Prove the orchestrator calls only accepted functions, writes nothing, preserves exact source hashes, and raises `CurrentRecoveryUnavailable` on a missing required source instead of substituting empty observations.

- [ ] **Step 2B: If any required current provider is absent, record the exact gate and stop this task**

Do not create a connector/network adapter in R8-C. The accepted supported behavior remains:

```python
agenda.build(..., recovery_assessment=<current assessment supplied by Sol/Control Room orchestration>)
```

and the weekly run reports `recovery_input.available=False` until an accepted current provider exists.

This branch is a legitimate stop condition, not a reason to weaken the architecture.

- [ ] **Step 3: If provider is built, run zero-write/network-boundary tests and commit**

```bash
python -m pytest tests/test_project_recovery_current.py -q
git add control_plane/project_recovery_current.py tests/test_project_recovery_current.py
git commit -m "feat(exec): compose current recovery assessment from accepted readers"
```

---

### Task 6: Reuse the existing weekly Agenda schedule without creating another job

**Files:**
- Modify `app/scheduler.py` only if Task 5 produced an accepted current provider.
- Modify/add the scheduler test file that already covers `improvement_agenda_weekly`.

**Interfaces:**
- Job id remains exactly `improvement_agenda_weekly`.
- Cron remains existing `AGENDA_WEEKLY_DAY` / `AGENDA_WEEKLY_UTC_HOUR` + minute 30.

- [ ] **Step 1: If Task 5 was held, prove scheduler is unchanged and skip implementation**

Run a source assertion/test that exactly one `improvement_agenda_weekly` job registration exists. Return weekly recovery ingestion as dependency-held; on-demand injection remains useful and accepted.

- [ ] **Step 2: If Task 5 built the provider, write RED existing-job integration test**

Monkeypatch `build_current_assessment()` to return a deterministic assessment, run `_improvement_agenda_job()`, and assert `improvement_agenda.write(prebuilt=...)` persists an Agenda containing the recovery item. Assert no second scheduler job id appears.

- [ ] **Step 3: Implement inside `_improvement_agenda_job()` only**

Conceptually:

```python
from brain import improvement_agenda
from control_plane.project_recovery_current import build_current_assessment
assessment = build_current_assessment(...current explicit args...)
prebuilt = improvement_agenda.build(recovery_assessment=assessment)
improvement_agenda.write(prebuilt=prebuilt)
```

If current assessment fails, catch it at the source boundary and build/write with `recovery_assessment=None` so the Agenda records degraded recovery input while preserving other sources.

- [ ] **Step 4: Run scheduler + Agenda regression suite**

Run:

```bash
python -m pytest tests/test_improvement_agenda.py -q
# plus the repository's existing scheduler test module selected by rg "improvement_agenda_weekly" tests/
```

Expected: one existing job, no new schedule, no execution side effects.

- [ ] **Step 5: Commit only if scheduler changed**

```bash
git add app/scheduler.py <scheduler-test> brain/improvement_agenda.py tests/test_improvement_agenda.py
git commit -m "feat(agenda): add recovery to existing weekly audit"
```

---

### Task 7: Current Agenda proof and stop

**Files:**
- Normal Agenda artifacts may be created only through the accepted `write()` path during proof.

- [ ] **Step 1: Build one Agenda from a real accepted R8-A current-estate assessment**

Record exact assessment semantic hash and exact Agenda date. Verify every `RECOVERY_REQUIRED`/`CEO_ATTENTION`/`UNKNOWN_RECONCILE` R8-A finding appears once with stable id and `owner=ceo-sol` where actionable.

- [ ] **Step 2: Verify non-actions**

Confirm the run creates no Executive Job/Attempt/Worker, no Linear mutation, no Slack message, no seat/prompt/config mutation and no second schedule.

- [ ] **Step 3: Require hosted CI and Sol review**

Return exact head, tests, Agenda receipt and whether weekly automatic current input is `LIVE` or `DEPENDENCY_HELD` based on Task 5.

**Stop condition:** recovery is ranked by the existing Agenda. Do not call the program fully permanent/proven until Control Room/projections and R8-G fresh-Sol canary are accepted.
