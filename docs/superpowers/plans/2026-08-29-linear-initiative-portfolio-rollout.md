# Linear Initiative Portfolio Rollout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deterministically normalize the current Agent OS → Linear Project projection, create exactly seven approved strategic Initiatives, attach exactly one primary Initiative to every eligible visible Project, preserve two explicit unassigned exceptions, and prove the resulting Linear portfolio by read-back without making Linear a canonical truth store.

**Architecture:** The existing Macro `scripts/linear_portfolio_plan.py` remains the only Project normalization compiler. Add one initiative-only deterministic planner that consumes its Project plan plus one static strategy companion and an externally captured read-only Linear Initiative snapshot; it performs zero network calls and zero writes. Live Linear mutation remains a separate, sequential, idempotent Sol apply phase using the current connected Linear surface unless the MAS-64/MAS-66 app-actor path is independently production-proven at execution time and can consume the exact same desired-state plan without widening scope.

**Tech Stack:** Python 3, JSON, pytest, existing `scripts.agentos` + `scripts.linear_portfolio_plan`, existing Macro CI-pack/unrun-suite guards, Linear connected Project/Initiative APIs for the one-time live apply.

**Spec:** `docs/superpowers/specs/2026-08-29-linear-initiative-portfolio-architecture-design.md`

## Global Constraints

- Chairman-approved design carrier: `Mastermind:sol/linear-initiative-portfolio-architecture-20260829`, approved spec head `c83d524d3785333fb2a92ee6e650a1477994be72`.
- Current protected procedure pin at plan authoring: `mastermindx-market-intelligence/Mastermind@19fe09ddbe065d57292effc2544edcbf447bfcc0`, Skillpack `mastermind.sol_skillpack.v1` v1.0.1, bootstrap-major 1 compatible.
- The protected advance from the spec's original pin `adccc544509aaa0ef7c0bb4f8bdbbfab19cf85e2` to `19fe09dd...` touches only Slack Agent Dialogue V2 engine/tests; it does not alter the Linear/portfolio architecture. Execution must re-pin again and re-evaluate if that ceases to be true.
- Current Macro pin at plan authoring: `mastermindx-market-intelligence/macro@8d641591ce8adb388b562e8c4edb65e3b61d76a6`.
- Current live Linear witness at plan authoring: 50 visible Projects, 0 Initiatives, every Project has zero Initiative parents. This is witness state only, not canonical truth.
- Agent OS remains organizational workstream truth; Executive OS remains Job/Attempt/Worker/Event truth; GitHub remains implementation/proof truth; Linear remains selected human portfolio projection; Slack remains dialogue/transport.
- Preserve exact capability vocabulary: `PROVEN_LIVE`, `BUILT_NOT_PROVEN`, `PARTIAL`, `DARK_OR_DISCONNECTED`, `BROKEN`, `SPEC_ONLY`, `NOT_BUILT`, `REJECTED_BY_DESIGN`.
- No fuzzy matching. A Project with canonical identity syntax `WS:<KEY>` binds only by that exact workstream key. `Mastermind-X Linear OS` binds only by its exact current Linear Project ID until canonical organizational ownership exists.
- Exactly seven v1 Initiatives; zero parent/sub-Initiatives; zero Initiative labels; zero new Project labels; zero target dates; Initiative owners unset; Initiative health unset at creation.
- Exactly one primary Initiative for every eligible visible Project. Multi-parent Initiative membership is forbidden in v1.
- Two explicit unassigned exceptions: `WS:WATCHLIST-PORTFOLIO-CEO` and current Linear Project ID `9aef6461-306a-4a3c-911b-c6a4b6635a78` (`Mastermind-X Linear OS`).
- Missing parked/done workstreams are not backfilled for aesthetics. Existing parked/done Projects already visible may retain strategic history membership without reactivation.
- The existing Project compiler owns Project desired name/summary/status. The Initiative implementation must not create a second Project naming, summary, lifecycle, issue, runtime, queue, retry, or identity pipeline.
- A GitHub merge, Linear status, Initiative rollup, or Slack `RESULT` never proves production acceptance.
- Any effect-unknown Linear write stops the batch immediately: re-read the exact target, reconcile, and never blind retry or switch carriers.
- Any new active workstream not classified by the approved strategy is a hard stop before live apply; return it to Sol/Chairman for explicit strategic classification.
- Any unexpected existing Initiative, confusingly similar Initiative name, Project with multiple Initiative parents, or manual Linear edit since snapshot is a hard reconciliation gate.
- Do not modify Issue projection, MAS-189, Executive Relay, Slack dialogue, Wake, runtime dispatch, app credentials, MAS-64, or MAS-66 as part of this rollout.

---

## File Structure

### Mastermind repository

- Existing approved design: `docs/superpowers/specs/2026-08-29-linear-initiative-portfolio-architecture-design.md`
- This implementation plan: `docs/superpowers/plans/2026-08-29-linear-initiative-portfolio-rollout.md`

These two files are the only files on the architecture/plan carrier before protected merge.

### Macro repository

- Create: `config/linear_initiative_portfolio.v1.json` — one machine-readable projection of the approved seven Initiative definitions, 50 exact workstream memberships and two explicit exceptions.
- Create: `scripts/linear_initiative_plan.py` — zero-network Initiative desired-state/drift compiler; imports and reuses `scripts.linear_portfolio_plan` rather than reimplementing Project selection or lifecycle law.
- Create: `tests/linear_initiative_plan_cases.py` — hermetic strategy/schema/drift tests.
- Create: `tests/linear_initiative_plan_live_cases.py` — real-checkout deterministic receipt over current Agent OS + committed witness fixture.
- Modify: `.github/ci/legacy-jobs.yml` — wire both new suites into the same bounded CI ownership family that already owns MAS-65/Agent OS portfolio-plan tests; do not waive them as unrun.
- Create during dry-run evidence step: `research/linear_initiative_portfolio/linear_initiative_snapshot_2026-08-29.json` — read-only normalized Linear witness.
- Create during dry-run evidence step: `research/linear_initiative_portfolio/linear_initiative_dry_run_2026-08-29.json` — planner receipt and exact intended creates/updates/memberships; evidence only, not a truth store.
- Create after accepted live rollout: `research/linear_initiative_portfolio/linear_initiative_post_apply_2026-08-29.json` — final normalized read-back witness.
- Create after accepted live rollout: `agentos/handoffs/AGENT-OS-2026-08-29-linear-initiative-portfolio-v1.md` — exact protected spec SHA, Macro planner SHA/hash, Linear Initiative IDs, Project counts, exceptions and next action; pointer/receipt only, not duplicate strategy prose.

---

### Task 0: Land the approved architecture and implementation plan on protected Mastermind

**Files:**
- Existing: `docs/superpowers/specs/2026-08-29-linear-initiative-portfolio-architecture-design.md`
- Existing: `docs/superpowers/plans/2026-08-29-linear-initiative-portfolio-rollout.md`

**Interfaces:**
- Consumes the Chairman-approved spec head `c83d524d3785333fb2a92ee6e650a1477994be72`.
- Produces one protected `master` commit containing the approved spec and this plan, with no runtime/Linear mutation.

- [ ] **Step 1: Re-pin protected Mastermind and inspect carrier movement**

Run from a clean checkout/worktree:

```bash
git fetch origin master
git rev-parse origin/master
git log --oneline --decorate -5 origin/master
git status --short
```

Expected: clean working tree. Compare current protected `docs/sol_skills/INDEX.md`, `COLD_START.md`, and `RECONCILE_STATE.md` from the same exact protected SHA. If compatibility changes from v1.0.1/bootstrap-major 1 or portfolio source law changed, STOP and return to Sol before rebasing.

- [ ] **Step 2: Reconcile the existing one-carrier branch, never create a sibling**

```bash
git switch sol/linear-initiative-portfolio-architecture-20260829
git log --oneline --decorate -5
git diff --name-only origin/master...HEAD
```

Expected changed paths before rebase are exactly:

```text
docs/superpowers/specs/2026-08-29-linear-initiative-portfolio-architecture-design.md
docs/superpowers/plans/2026-08-29-linear-initiative-portfolio-rollout.md
```

If the branch has unexpected commits/files, classify the movement before proceeding. Do not reset or force-push over unknown work.

- [ ] **Step 3: Rebase only if the current protected delta is non-conflicting**

```bash
git rebase origin/master
```

If a conflict touches either portfolio spec/plan or a newer portfolio/source-law artifact, STOP for Sol review. Do not resolve strategic text by choosing one side mechanically.

- [ ] **Step 4: Verify records-only scope after rebase**

```bash
git diff --name-only origin/master...HEAD
git diff --check origin/master...HEAD
```

Expected: exactly the two docs above; zero whitespace errors.

- [ ] **Step 5: Open one draft PR and run normal protected checks**

PR title:

```text
[DESIGN][PLAN] Linear Initiative portfolio architecture v1
```

PR body must state: seven Initiatives; no Linear mutation; no runtime; no labels/sub-Initiatives; one-primary-membership law; two explicit exceptions; live apply withheld until later tasks.

- [ ] **Step 6: Review/merge the records carrier, then capture the source-design revision**

After protected merge:

```bash
git fetch origin master
PROTECTED_SPEC_SHA=$(git rev-parse origin/master)
printf '%s\n' "$PROTECTED_SPEC_SHA"
```

Require exactly one 40-hex SHA and verify the approved spec exists at that revision before using the value in Task 1. Do not treat green CI as rollout acceptance.

---

### Task 1: Freeze the machine-readable Initiative strategy companion

**Files:**
- Create: `config/linear_initiative_portfolio.v1.json`
- Create: `scripts/linear_initiative_plan.py`
- Create: `tests/linear_initiative_plan_cases.py`

**Interfaces:**
- Produces `STRATEGY_SCHEMA = "linear_initiative_portfolio_strategy.v1"`.
- Produces `InitiativePlanError(failures: Sequence[Mapping[str, Any]])` with machine-readable failure rows.
- Produces `load_strategy(path: Path) -> dict[str, Any]`.
- Produces `validate_strategy(strategy: Mapping[str, Any], project_plan: Mapping[str, Any]) -> None`.
- Imports `scripts.linear_portfolio_plan as lpp`; it must not reimplement `ACTIVE`, `EXCLUDED`, Project names, summaries, or status mapping.

- [ ] **Step 1: Write RED tests for the frozen v1 strategy shape**

Create `tests/linear_initiative_plan_cases.py` with literal expectations for:

```python
EXPECTED_INITIATIVES = {
    "canonical-intelligence-substrate-learning": ("Canonical Intelligence Substrate & Learning", 2),
    "legendary-alpha-discovery-timing": ("Legendary Alpha Discovery & Timing", 1),
    "institutional-company-event-intelligence": ("Institutional Company & Event Intelligence", 2),
    "global-markets-regimes-risk-command": ("Global Markets, Regimes & Risk Command", 2),
    "personal-institutional-desk": ("Personal Institutional Desk", 1),
    "trusted-production-customer-platform": ("Trusted Production & Customer Platform", 2),
    "autonomous-ai-organization": ("Autonomous AI Organization", 1),
}
```

Assert for every Initiative:

```python
assert row["status"] == "Active"
assert row["lead_team"] == "MastermindX"
assert row["owner"] is None
assert row["target_date"] is None
assert row["health"] is None
assert row["labels"] == []
assert row["parent_initiatives"] == []
```

Assert exactly 50 `WS:` membership rows and exactly two exceptions. Assert the membership group counts are exactly `9, 14, 11, 5, 3, 5, 3`. Assert the exceptions are exactly:

```python
{
    ("workstream_key", "WS:WATCHLIST-PORTFOLIO-CEO", "compatibility_redirect"),
    ("linear_project_id", "9aef6461-306a-4a3c-911b-c6a4b6635a78", "canonical_parent_unresolved"),
}
```

Assert no workstream appears in more than one Initiative and the Watchlist redirect appears in no membership row.

- [ ] **Step 2: Run the focused suite and observe RED**

```bash
python3 -m pytest -q tests/linear_initiative_plan_cases.py
```

Expected: import/file failure because the module/config do not exist.

- [ ] **Step 3: Create the exact strategy JSON from the protected spec**

Construct this Python object, using `PROTECTED_SPEC_SHA` captured by Task 0:

```python
strategy = {
    "schema": "linear_initiative_portfolio_strategy.v1",
    "source_design": {
        "repository": "mastermindx-market-intelligence/Mastermind",
        "path": "docs/superpowers/specs/2026-08-29-linear-initiative-portfolio-architecture-design.md",
        "protected_revision": PROTECTED_SPEC_SHA,
    },
    "initiatives": [],
    "memberships": {},
    "unassigned_exceptions": [],
}
```

Write the resulting JSON with sorted keys and a trailing newline. `protected_revision` must be the exact command output captured in Task 0; never type or guess it manually.

For each Initiative store the exact approved `name`, `summary`, `outcome`, `moat`, `completion_ruler`, `scope_law`, `status`, numeric `priority`, `lead_team`, null `owner`, null `target_date`, null `health`, empty `labels`, and empty `parent_initiatives`. Copy the approved prose exactly from spec §8.1–§8.7. The planner renders description deterministically as:

```python
return (
    f"Outcome: {row['outcome']}\n\n"
    f"Moat: {row['moat']}\n\n"
    f"Completion ruler: {row['completion_ruler']}\n\n"
    f"Scope law: {row['scope_law']}"
)
```

- [ ] **Step 4: Implement closed schema/strategy validation only**

In `scripts/linear_initiative_plan.py`:

```python
STRATEGY_SCHEMA = "linear_initiative_portfolio_strategy.v1"
PLAN_SCHEMA = "linear_initiative_plan.v1"
RECEIPT_SCHEMA = "linear_initiative_plan_receipt.v1"
SNAPSHOT_SCHEMA = "linear_initiative_snapshot.v1"

class InitiativePlanError(RuntimeError):
    def __init__(self, failures):
        self.failures = tuple(failures)
        super().__init__(f"linear initiative plan refused: {len(self.failures)} hard defect(s)")


def load_strategy(path: Path) -> dict[str, Any]:
    doc = json.loads(path.read_text(encoding="utf-8"))
    if doc.get("schema") != STRATEGY_SCHEMA:
        raise InitiativePlanError([{"code": "strategy_wrong_schema"}])
    return doc
```

`validate_strategy()` must refuse at least these codes:

```text
strategy_initiative_count_mismatch
strategy_duplicate_initiative_key
strategy_duplicate_initiative_name
strategy_initiative_field_mismatch
strategy_membership_count_mismatch
strategy_duplicate_membership
strategy_unknown_initiative_key
strategy_unmapped_active_workstream
strategy_exception_mismatch
strategy_exception_also_mapped
strategy_membership_unknown_workstream
```

Use the Project plan's exact workstream keys as the workstream universe. `WS:WATCHLIST-PORTFOLIO-CEO` is allowed to be active and unmapped only because it is the exact explicit exception. Do not infer exceptions from titles/programs.

- [ ] **Step 5: Run GREEN**

```bash
python3 -m pytest -q tests/linear_initiative_plan_cases.py
python3 -m py_compile scripts/linear_initiative_plan.py
```

- [ ] **Step 6: Commit the strategy substrate**

```bash
git add config/linear_initiative_portfolio.v1.json scripts/linear_initiative_plan.py tests/linear_initiative_plan_cases.py
git commit -m "feat(linear): freeze Initiative portfolio strategy v1"
```

---

### Task 2: Add deterministic Initiative desired-state and drift compilation

**Files:**
- Modify: `scripts/linear_initiative_plan.py`
- Modify: `tests/linear_initiative_plan_cases.py`
- Create: `tests/linear_initiative_plan_live_cases.py`
- Modify: `.github/ci/legacy-jobs.yml`

**Interfaces:**
- Produces `render_description(row: Mapping[str, Any]) -> str`.
- Produces `compile_initiative_plan(*, project_plan: Mapping[str, Any], strategy_path: Path, snapshot_path: Path | None = None) -> tuple[dict[str, Any], dict[str, Any]]`.
- Produces `initiative_drift(snapshot, desired_initiatives, desired_memberships, exceptions) -> list[dict[str, Any]]`.
- Produces zero network calls and zero Linear writes.

- [ ] **Step 1: Add RED tests for deterministic desired state**

Use synthetic Project-plan fixtures with active/done/parked workstreams and a synthetic Initiative snapshot. Assert:

```python
plan, receipt = lip.compile_initiative_plan(
    project_plan=project_plan,
    strategy_path=strategy_path,
    snapshot_path=snapshot_path,
)
repeat, _ = lip.compile_initiative_plan(
    project_plan=project_plan,
    strategy_path=strategy_path,
    snapshot_path=snapshot_path,
)
assert plan["schema"] == "linear_initiative_plan.v1"
assert len(plan["desired_initiatives"]) == 7
assert len(plan["desired_memberships"]) == 50
assert len(plan["unassigned_exceptions"]) == 2
assert plan["semantic_hash"] == repeat["semantic_hash"]
```

Prove absent done/parked workstreams are not marked `project_create_required`, while missing active mapped workstreams are. Prove `Mastermind-X Linear OS` is matched only by exact Project ID. Prove `WS:WATCHLIST-PORTFOLIO-CEO` remains unassigned even though active.

- [ ] **Step 2: Add RED drift tests**

Pin these warning/failure codes:

```text
initiative_missing
unexpected_initiative
initiative_field_drift
initiative_name_ambiguous
project_create_required
project_binding_missing
project_binding_ambiguous
membership_missing
membership_wrong
membership_multi_parent
exception_has_forbidden_membership
unmapped_visible_project
```

`unexpected_initiative`, `initiative_name_ambiguous`, `membership_multi_parent`, `exception_has_forbidden_membership`, `unmapped_visible_project`, and any unclassified active workstream are hard apply blockers.

- [ ] **Step 3: Observe RED**

```bash
python3 -m pytest -q tests/linear_initiative_plan_cases.py
```

- [ ] **Step 4: Implement the snapshot and planner contract**

Accepted witness schema:

```json
{
  "schema": "linear_initiative_snapshot.v1",
  "source": {"authority": "witness_only_not_canonical"},
  "initiatives": [
    {
      "initiative_id": "11111111-1111-1111-1111-111111111111",
      "name": "Example Initiative",
      "status": "Active",
      "priority": 1,
      "health": null,
      "owner_id": null,
      "lead_team": "MastermindX",
      "target_date": null,
      "labels": [],
      "parent_initiative_ids": []
    }
  ],
  "projects": [
    {
      "project_id": "22222222-2222-2222-2222-222222222222",
      "workstream_key": "WS:EXACT-KEY",
      "name": "WS:EXACT-KEY — Exact title",
      "status_class": "started",
      "initiative_ids": [],
      "initiative_names": []
    }
  ]
}
```

The UUIDs above are synthetic fixture values only. `workstream_key` is null only for a Project that has no exact accepted `WS:` binding. Never derive it by fuzzy title matching.

Desired Initiative rows contain exact name/summary/rendered description/status/priority/lead team/null owner/null target/empty labels/empty parents/null initial health. Desired membership rows contain exact Project binding plus exactly one strategy key.

- [ ] **Step 5: Keep Project compilation unchanged**

Add a test that imports `scripts.linear_portfolio_plan`, compiles the same fixture before/after Initiative work and asserts the existing `linear_portfolio_plan.v1` semantic JSON is unchanged. The Initiative module may call/reuse it; it may not modify its selection law or schema in this task.

- [ ] **Step 6: Add real-checkout Initiative receipt**

`tests/linear_initiative_plan_live_cases.py` must load current committed Agent OS through `lpp.compile_plan()`, load `config/linear_initiative_portfolio.v1.json`, and optionally load the committed Initiative witness fixture under `research/linear_initiative_portfolio/` when present. Emit a CI receipt containing strategy source revision, Project-plan semantic hash, Initiative-plan semantic hash, desired counts, group counts, exception bindings and drift-code counts.

- [ ] **Step 7: Wire the new tests into existing CI ownership**

Run first:

```bash
python3 scripts/audit_unrun_tests.py
```

Expected before wiring: both new test modules are named as unrun. Add them to the same CI-pack job/step family that already executes MAS-65 Agent OS/Linear portfolio-plan tests. Do not add a new always-on CI control plane merely for these two files.

Run after wiring:

```bash
python3 scripts/audit_unrun_tests.py
```

Expected: zero introduced unrun findings for the new files.

- [ ] **Step 8: Run complete focused verification**

```bash
python3 -m pytest -q tests/linear_portfolio_plan_cases.py tests/linear_portfolio_plan_live_cases.py tests/linear_initiative_plan_cases.py tests/linear_initiative_plan_live_cases.py
python3 -m py_compile scripts/linear_portfolio_plan.py scripts/linear_initiative_plan.py
```

- [ ] **Step 9: Commit**

```bash
git add scripts/linear_initiative_plan.py tests/linear_initiative_plan_cases.py tests/linear_initiative_plan_live_cases.py .github/ci/legacy-jobs.yml
git commit -m "feat(linear): compile Initiative desired state and drift"
```

---

### Task 3: Reconcile current canonical Agent OS state and produce the fresh dry-run witness

**Files:**
- Modify only if independently proven stale: `agentos/workstreams/WS-*.md`
- Create/update evidence: `research/linear_initiative_portfolio/linear_initiative_snapshot_2026-08-29.json`
- Create: `research/linear_initiative_portfolio/linear_initiative_dry_run_2026-08-29.json`

**Interfaces:**
- Consumes current protected Skillpack, current Macro main, current Agent OS direct records, current GitHub evidence, and fresh read-only Linear Projects/Initiatives.
- Produces one exact pre-mutation dry-run with no unresolved hard blockers.

- [ ] **Step 1: Re-pin current protected procedure and current Macro main**

Record exact SHAs. If the approved design spec is not on protected Mastermind `master`, STOP. If Macro changed the Project projector/source law materially since Tasks 1–2, rebase/review before continuing.

- [ ] **Step 2: Regenerate/read current Agent OS state and validate**

```bash
python3 scripts/agentos.py validate
python3 scripts/agentos.py status --scan-uncommitted
```

Do not edit generated `docs/AGENT_OS_STATE.md` by hand.

- [ ] **Step 3: Adjudicate the known disagreement families against proof law**

At minimum inspect:

```text
WS:RATES-INFLATION-COMMAND
WS:CYCLE-PATTERN-ISSUER-MECHANISM
WS:DEFENSE-PROCUREMENT-V3
WS:CAPITAL-STRUCTURE-INTELLIGENCE-V2
WS:FINANCIAL-INTELLIGENCE-FABRIC
WS:INTRADAY-FLOW-P0-RECOVERY
```

Rules:

- merged implementation alone never closes a proof-gated wave;
- if a direct record is demonstrably stale, repair that direct record on one bounded records carrier before Linear apply;
- if the evidence does not support a unique canonical correction, preserve an explicit unresolved disagreement and do not invent a status;
- `BIOCATALYST-CORE-PRODUCT`, `FUNDAMENTAL-FORENSICS`, `EVAL-OS-OUTPUT-HEALTH`, and the four blocked workstreams already have canonical statuses; their mismatch is a Linear projection repair, not Agent OS work.

If Agent OS corrections are needed, run validation, open one records-only PR, obtain review/merge, then restart this Task from Step 1 on the new current Macro main. If no corrections are needed, do not make a no-op records commit.

- [ ] **Step 4: Capture a fresh normalized Linear witness with zero writes**

Use current Linear reads only:

```text
list_projects(limit=50, includeArchived=true, fields=id,name,summary,status,priority,initiatives,teams,updatedAt)
list_initiatives(limit=50, includeArchived=true, fields=id,name,status,priority,health,updatedAt)
```

If Project pagination appears, read every page. Normalize exact Project IDs, exact `WS:` prefixes, status classes and current Initiative membership into `research/linear_initiative_portfolio/linear_initiative_snapshot_2026-08-29.json`. Preserve `Mastermind-X Linear OS` with `workstream_key: null` and its exact Project ID.

- [ ] **Step 5: Run Project and Initiative dry-runs**

```bash
python3 -m pytest -q tests/linear_portfolio_plan_live_cases.py tests/linear_initiative_plan_live_cases.py
```

Also invoke the planner module/entrypoint added in Task 2 to write `research/linear_initiative_portfolio/linear_initiative_dry_run_2026-08-29.json` containing the exact Project field updates, the two Project creates if still missing/eligible, seven Initiative creates if still absent, 50 desired memberships, and two unassigned exceptions.

- [ ] **Step 6: Enforce the pre-apply stop condition**

Proceed only if all are true:

```text
0 unexpected Initiatives
0 confusing/ambiguous Initiative names
0 multi-parent Project memberships
0 exception membership violations
0 unclassified active workstreams
0 unmapped visible Projects beyond the two frozen exceptions
0 ambiguous Project bindings
7 desired Initiatives
2 or fewer active Project creates, and only TOP-ANATOMY / EVAL-OS-EVIDENCE-VIEW when still canonically active+missing
```

Any other state returns to Sol/Chairman before mutation.

- [ ] **Step 7: Commit the dry-run evidence**

```bash
git add research/linear_initiative_portfolio/linear_initiative_snapshot_2026-08-29.json research/linear_initiative_portfolio/linear_initiative_dry_run_2026-08-29.json
git commit -m "docs(linear): freeze Initiative rollout dry run"
```

The evidence commit grants no Linear write authority by itself.

---

### Task 4: Normalize the live Linear Project projection and create only the two missing active Projects

**Files:**
- No repository code changes during the live mutation itself.
- Evidence after apply is recorded in Task 7/8.

**Interfaces:**
- Consumes the exact dry-run Project desired state from Task 3.
- Produces a live Linear Project estate whose managed name/summary/status agrees with the current deterministic Project plan or carries a deliberate unresolved disagreement.

- [ ] **Step 1: Re-read every Project target immediately before mutation**

Compare `updatedAt`, exact ID, name, status and current Initiatives to the Task-3 witness. If any target changed, regenerate the affected dry run. Do not overwrite a manual edit merely to finish the batch.

- [ ] **Step 2: Apply only deterministic Project fields**

For each existing exact `WS:` Project, update only fields actually different from the fresh `linear_portfolio_plan.v1` desired state:

```text
name
summary
state
```

Do not modify Project priority, lead, labels, milestones, arbitrary human description text or Issue state in this migration unless a separately proven existing app-actor managed-block contract requires it.

Map desired status classes to live Project states:

```text
started   -> In Progress
paused    -> Paused
completed -> Completed
canceled  -> Canceled
candidate -> Planned
```

If the live workspace refuses one of these state names, STOP and reconcile the actual status vocabulary; never substitute a semantically different state.

- [ ] **Step 3: Create `WS:TOP-ANATOMY` only if still active and still absent**

Exact name is generated by current Project compiler from canonical workstream title. Use `MastermindX` team, desired summary, and desired `In Progress` state. Leave priority/lead/labels/target date unset rather than inventing them. Capture returned Project ID into the live apply receipt and immediately re-read that exact ID.

If an exact or confusingly similar Project appeared after snapshot, do not create a duplicate.

- [ ] **Step 4: Create `WS:EVAL-OS-EVIDENCE-VIEW` only if still active and still absent**

Use the same rules as Step 3. Capture the returned Project ID into the live apply receipt and immediately re-read that exact ID.

- [ ] **Step 5: Bound the batch and stop on effect-unknown**

Apply in exact workstream-key sort order. After every 10 successful writes, re-list Projects and confirm all written targets have expected name/summary/state. On any timeout/ambiguous response, stop immediately and re-read the exact Project ID; do not issue a second write until effect is known.

- [ ] **Step 6: Project-normalization acceptance read**

Require:

```text
all exact WS bindings unique
all canonical blocked/parked visible Projects project as Paused
all canonical done visible Projects project as Completed
TOP-ANATOMY and EVAL-OS-EVIDENCE-VIEW exist if still eligible
WATCHLIST-PORTFOLIO-CEO still exists as compatibility redirect and is not reactivated into old scope
Mastermind-X Linear OS remains untouched except for later Initiative-unassignment verification
```

Only after this read succeeds may Initiative objects be created.

---

### Task 5: Create exactly seven live Initiatives with frozen metadata

**Files:**
- No repository changes during live mutation.

**Interfaces:**
- Consumes the exact seven desired Initiative rows from `linear_initiative_plan.v1`.
- Produces seven Initiative IDs bound to exact approved names.

- [ ] **Step 1: Re-list Initiatives immediately before creation**

Expected on the current baseline: zero. If any Initiative exists, compare by exact ID/name/fields. Any unexpected or confusingly similar name is a hard reconciliation stop; never suffix a duplicate name.

- [ ] **Step 2: Create Initiatives sequentially in strategy-key order**

For each exact desired row call the live Initiative create path with:

```text
name: exact frozen name
summary: exact frozen summary
description: deterministic Outcome/Moat/Completion ruler/Scope law rendering
status: Active
priority: exact numeric priority
leadTeam: MastermindX
owner: null
labels: []
parentInitiatives: omitted
targetDate: omitted
```

Do not set health during creation.

- [ ] **Step 3: Re-read each created Initiative before creating the next**

Verify exact name, summary, description, status, priority, lead team, null owner, null target, empty labels and no parents. Store its returned stable Initiative ID in an in-memory `initiative_id_by_strategy_key` map and in the live apply receipt.

On effect-unknown, stop and re-list/get the exact target by name/ID before any retry.

- [ ] **Step 4: Seven-Initiative creation gate**

Proceed only when a fresh list shows exactly the seven approved names and no extra Initiative created by this operation.

---

### Task 6: Apply the 50 exact primary Project → Initiative memberships

**Files:**
- No repository changes during live mutation.

**Interfaces:**
- Consumes exact Project IDs plus `initiative_id_by_strategy_key: dict[str, str]` from Task 5.
- Produces exactly 50 one-parent Project memberships and exactly two visible unassigned exceptions.

- [ ] **Step 1: Resolve the two newly created Project IDs**

Bind returned IDs from Task 4 to `WS:TOP-ANATOMY` and `WS:EVAL-OS-EVIDENCE-VIEW`; never discover them by approximate title search.

- [ ] **Step 2: Apply memberships one Initiative group at a time**

For each membership row, resolve `initiative_id = initiative_id_by_strategy_key[strategy_key]` and call Project `setInitiatives: [initiative_id]`; never use additive attachment. Group order and expected counts:

```text
Canonical Intelligence Substrate & Learning: 9
Legendary Alpha Discovery & Timing: 14
Institutional Company & Event Intelligence: 11
Global Markets, Regimes & Risk Command: 5
Personal Institutional Desk: 3
Trusted Production & Customer Platform: 5
Autonomous AI Organization: 3
```

After each group, re-list/filter the Initiative's Projects and verify exact set equality before moving to the next group.

- [ ] **Step 3: Enforce the two exceptions explicitly**

Ensure both have zero Initiative parents:

```text
8c6fa965-f076-4fe2-ae79-5e1bc9e17cea  WS:WATCHLIST-PORTFOLIO-CEO
9aef6461-306a-4a3c-911b-c6a4b6635a78  Mastermind-X Linear OS
```

Do not assign `Mastermind-X Linear OS` based on the current likely strategy. Canonical organizational ownership must be established first.

- [ ] **Step 4: Stop on any multi-parent or moved Project**

If a Project acquires another Initiative parent during the batch, or `updatedAt` changes unexpectedly, stop and reconcile rather than overwriting unknown concurrent work.

---

### Task 7: Read-back acceptance and first truthful Initiative updates

**Files:**
- Create/update evidence only after successful structural apply: `research/linear_initiative_portfolio/linear_initiative_post_apply_2026-08-29.json`

**Interfaces:**
- Produces the final read-back acceptance receipt.
- Optionally produces one strategic status update per Initiative; health is set only where fresh evidence supports it.

- [ ] **Step 1: Capture a complete post-apply snapshot**

Read all seven Initiatives including Projects and read all Projects including Initiative relations. Normalize to the same `linear_initiative_snapshot.v1` schema.

- [ ] **Step 2: Run the deterministic planner against post-apply state**

Expected drift:

```text
0 initiative_missing
0 unexpected_initiative
0 initiative_field_drift
0 project_create_required
0 membership_missing
0 membership_wrong
0 membership_multi_parent
0 exception_has_forbidden_membership
0 unmapped_visible_project
```

Project desired-state drift must likewise be zero or explicitly documented as an unresolved canonical disagreement, never silently ignored.

- [ ] **Step 3: Verify exact structural acceptance counts**

```text
7 Initiatives
0 Initiative labels created
0 parent/sub-Initiative relations
52 visible Projects if both planned creates remained eligible and no new concurrent Project appeared
50 Projects with exactly one Initiative
2 explicit unassigned exceptions
0 Initiative target dates
0 Initiative owners invented
0 health values invented at creation
```

If current company state legitimately added/removed work between dry-run and apply, do not force these historical counts; stop earlier and regenerate the strategy/dry-run. These are acceptance counts for one frozen apply epoch, not permanent quotas.

- [ ] **Step 4: Compose one fresh executive status update per Initiative**

For each Initiative, read its current canonical Project frontiers and write concise prose with exactly these semantic fields:

```text
Material change
Current strategic frontier
Largest blocker / risk
Next company-level dependency
Evidence / proof that changed the assessment
```

Do not dump PR-by-PR activity.

- [ ] **Step 5: Set health only when evidence supports a real strategic ruling**

Use:

```text
On track  -> frontier is advancing; no known blocker materially threatens outcome
At risk   -> viable path exists, but material blocker/proof/authority/dependency threatens outcome
Off track -> current path cannot achieve outcome without architecture/authority/product correction
```

If evidence is insufficient or mixed, publish the update without a health field and leave health unset. Do not average child statuses.

- [ ] **Step 6: Commit the post-apply receipt**

```bash
git add research/linear_initiative_portfolio/linear_initiative_post_apply_2026-08-29.json
git commit -m "docs(linear): record Initiative portfolio v1 acceptance"
```

---

### Task 8: Durable organizational closeout

**Files:**
- Create: `agentos/handoffs/AGENT-OS-2026-08-29-linear-initiative-portfolio-v1.md`
- Modify only if independently warranted: the canonical Agent OS workstream that owns the portfolio projection continuation; do not mint a new workstream just for this rollout.

**Interfaces:**
- Produces a concise durable pointer from Agent OS to the protected strategy spec, Macro planner proof and live Linear IDs.
- Does not duplicate the seven strategic definitions as a second source.

- [ ] **Step 1: Write the closeout handoff**

Record:

```text
protected Mastermind spec SHA/path
Macro planner merge SHA
linear_initiative_plan semantic hash
seven Initiative names + stable Linear IDs
post-apply Project count
50 primary memberships
2 explicit exceptions
post-apply snapshot path/hash
any Initiative health values actually set
any deliberately unresolved Project/Agent OS disagreement
exact next action
```

Link the approved spec for strategy semantics rather than copying its full prose.

- [ ] **Step 2: Validate Agent OS**

```bash
python3 scripts/agentos.py validate
```

- [ ] **Step 3: Run final focused tests on the exact closeout head**

```bash
python3 -m pytest -q tests/linear_portfolio_plan_cases.py tests/linear_portfolio_plan_live_cases.py tests/linear_initiative_plan_cases.py tests/linear_initiative_plan_live_cases.py
python3 scripts/audit_unrun_tests.py
```

Expected: all focused suites green; zero introduced unrun-suite findings.

- [ ] **Step 4: Independent review and merge**

Review against the protected strategy spec, Project-management operating-surface cutover law and current Skillpack. The closeout merge proves durable records only; the live Linear read-back from Task 7 is the portfolio acceptance evidence.

---

## Appendix A — Current exact Linear Project bindings and approved primary homes

These IDs are the fresh plan-authoring witness and must be re-read before apply. If an ID/name binding changes, regenerate the dry run instead of reusing this table blindly.

### Canonical Intelligence Substrate & Learning — 9

| Workstream | Current Linear Project ID |
|---|---|
| `WS:ALPHA-INTELLIGENCE-INTEGRATION` | `b1df7e13-af86-417e-b184-8c4c4de41db1` |
| `WS:GMI-THEME-GRAPH` | `b14865fe-dcf3-47be-9b13-d8ac3c5283ed` |
| `WS:STOCK-IDENTITY` | `bbc7fd3f-c98b-47f9-9edb-8a6d749545a5` |
| `WS:MARKET-MEMORY-W2C` | `26a8e9bc-06ba-4c69-bbf9-654bee8d9f2d` |
| `WS:MASSIVE-STOCK-DAY-R2-COHERENCE` | `85f6712e-932f-435a-a460-c5acbb40ee83` |
| `WS:EVAL-OS-MEASUREMENT-LAW` | `fa76a2e6-a3bb-48c3-a78f-ee71be89fa17` |
| `WS:EVAL-OS-EVIDENCE-VIEW` | returned Project ID from Task 4 Step 4; no preexisting ID at plan authoring |
| `WS:EVAL-OS-T1-ENGINE-REGISTRY` | `8b73301b-9891-401a-a25d-2b0664d7c969` |
| `WS:EVAL-OS-OUTPUT-HEALTH` | `fdf383ee-d1ab-4340-98ca-3e0f962bdf71` |

### Legendary Alpha Discovery & Timing — 14

| Workstream | Current Linear Project ID |
|---|---|
| `WS:ADVANCED-DATA-OPTIONS` | `e5abdbb7-45ee-4774-8202-49c7dba5e22c` |
| `WS:OPTIONS-ALPHA-INTELLIGENCE-RECOVERY` | `8524ca70-6f09-4d92-8bfd-5e56fef47fea` |
| `WS:INTRADAY-FLOW-P0-RECOVERY` | `111b98b9-7de5-4a03-a654-19e14fe748cb` |
| `WS:OPTIONS-CONTEXT-AUDIT-PREREG-V2` | `4d8ab8ae-3675-4ec8-afc3-21d0e95a503f` |
| `WS:CHINA-ALPHA-INTELLIGENCE` | `f4668418-ffa6-4972-8d05-b2f3b2129005` |
| `WS:CN-LIMIT-ALPHA` | `75ff851f-a07c-4fb1-b826-75e8220a8cc1` |
| `WS:PROPHET-CONDITIONAL-FUSION` | `5b800484-e307-4fb8-b856-dbfa45d0506d` |
| `WS:PROPHET-HK-CA-REVAMP` | `cd2ef96d-7892-4f51-9c75-2dc16df60a38` |
| `WS:PROPHET-US-AVAILABILITY` | `6ea4bc57-9cda-4780-a639-70479858a69c` |
| `WS:PROPHET-US-ENTRY-TIMING` | `ee97a897-0852-45ee-b161-d8265619db87` |
| `WS:PROPHET-US-V4-RECOVERY` | `9415ebb1-cda0-44be-9aed-d2d35c3529c9` |
| `WS:LIVE-ENTRY-RADAR` | `a3d0511d-be67-4b7f-9f79-38f15a810812` |
| `WS:BREATHING-PLATFORM` | `68a27433-7bf2-4300-99bd-36c7ac63f93a` |
| `WS:TOP-ANATOMY` | returned Project ID from Task 4 Step 3; no preexisting ID at plan authoring |

### Institutional Company & Event Intelligence — 11

| Workstream | Current Linear Project ID |
|---|---|
| `WS:EARNINGS-EVENT-INTELLIGENCE-COMPILER` | `16951d05-0468-4c3e-b4bd-00212b54d21c` |
| `WS:FINANCIAL-INTELLIGENCE-FABRIC` | `2bbb6e6b-8394-4c35-8089-2fd673560e99` |
| `WS:CALCBENCH-FILING-FORENSICS-PARITY` | `d9a40850-72ea-4b7c-a9e4-87b9dd22c59c` |
| `WS:CAPITAL-STRUCTURE-INTELLIGENCE-V2` | `ccae793b-deed-4709-b6e2-90752634e188` |
| `WS:DEFENSE-PROCUREMENT-V3` | `ab6596c4-b2dd-4004-85ae-2821dd6ee658` |
| `WS:BPC-JV-RECON` | `526f6876-5294-4124-a80c-f8a7ceacb9e4` |
| `WS:CN-SOE-DEMAND` | `8f2b7fa1-9d1b-4702-97fc-49612127efaa` |
| `WS:BIOCATALYST-CORE-PRODUCT` | `4c6706cb-edff-48f2-abcd-0c7045f1723b` |
| `WS:BIOCATALYST-RECOVERY-V2` | `71f68fd3-f862-4e40-a1ee-51e7949cfa1e` |
| `WS:EARNINGS-INTELLIGENCE-OS` | `743a83df-3709-407f-986a-ce3f988b9531` |
| `WS:FUNDAMENTAL-FORENSICS` | `7e33bea9-34a7-4051-953c-65e36fb57800` |

### Global Markets, Regimes & Risk Command — 5

| Workstream | Current Linear Project ID |
|---|---|
| `WS:RATES-INFLATION-COMMAND` | `ef62f66d-d4c2-4b46-9b48-13722dd57a65` |
| `WS:MACRO-CONTEXT-INDEX` | `6c2b1694-b7ae-487a-8ae8-7e31178ac224` |
| `WS:GREY-DEER-RISK-INTELLIGENCE` | `282d4ef7-bd99-4f03-813b-c0dbac898365` |
| `WS:CRYPTO-INTELLIGENCE` | `8cac67ff-5b74-47ba-86d1-81a0cf2ecb9b` |
| `WS:CYCLE-PATTERN-ISSUER-MECHANISM` | `fbd28d51-3d1b-4e54-a2f6-3df7c53aee7c` |

### Personal Institutional Desk — 3

| Workstream | Current Linear Project ID |
|---|---|
| `WS:MARKET-OS` | `b2be8a55-897b-4f4f-aace-bd62994f20b4` |
| `WS:STOCK-DOSSIER-LIVE-QUOTE` | `e603e810-a620-430b-a660-4873e8e1b9ec` |
| `WS:INSTITUTIONAL-PRODUCT-EXPERIENCE-V2` | `c9e8ea6b-0a12-4ef5-a8c6-8897c6564198` |

### Trusted Production & Customer Platform — 5

| Workstream | Current Linear Project ID |
|---|---|
| `WS:ACCOUNT-IDENTITY-HARDENING` | `61fce18e-793b-4447-b618-4b0062d88862` |
| `WS:CUSTOMER-DATA-BACKUP` | `3d9250a1-a52c-4eb2-ae0a-5cddb9aca0d6` |
| `WS:COMMERCIAL-PATH-ALERTING` | `8e2288f2-432e-4b3d-a0e8-866a799b13e3` |
| `WS:CI-MERGE-CONTROL-PLANE` | `32a37154-e0df-4592-8385-5cb251d4dec3` |
| `WS:RUNNER-FLEET-RESILIENCE` | `faa21e4b-b1db-4c6e-a2fb-8fb7027a0e5e` |

### Autonomous AI Organization — 3

| Workstream | Current Linear Project ID |
|---|---|
| `WS:AGENT-OS` | `3e16680c-5549-485d-a056-e07d69eaaf43` |
| `WS:CHAIRMAN-CONTROL-ROOM` | `0cd5fc91-db1d-4f18-a3d1-3a3a4433f226` |
| `WS:EXECUTIVE-CAPACITY-FABRIC` | `ec370898-f812-4291-bad1-cf8da312ad30` |

### Explicit unassigned exceptions — 2

| Binding | Current Linear Project ID | Reason |
|---|---|---|
| `WS:WATCHLIST-PORTFOLIO-CEO` | `8c6fa965-f076-4fe2-ae79-5e1bc9e17cea` | compatibility redirect to Market OS |
| `Mastermind-X Linear OS` | `9aef6461-306a-4a3c-911b-c6a4b6635a78` | canonical organizational parent unresolved |

---

## Appendix B — Exact Initiative metadata

The full exact approved prose is in spec §8.1–§8.7 and must be copied byte-for-byte into the strategy companion fields. The live Initiative description is rendered deterministically from those fields; do not paraphrase during apply.

| Strategy key | Name | Priority | Status | Lead team |
|---|---|---:|---|---|
| `canonical-intelligence-substrate-learning` | Canonical Intelligence Substrate & Learning | 2 / High | Active | MastermindX |
| `legendary-alpha-discovery-timing` | Legendary Alpha Discovery & Timing | 1 / Urgent | Active | MastermindX |
| `institutional-company-event-intelligence` | Institutional Company & Event Intelligence | 2 / High | Active | MastermindX |
| `global-markets-regimes-risk-command` | Global Markets, Regimes & Risk Command | 2 / High | Active | MastermindX |
| `personal-institutional-desk` | Personal Institutional Desk | 1 / Urgent | Active | MastermindX |
| `trusted-production-customer-platform` | Trusted Production & Customer Platform | 2 / High | Active | MastermindX |
| `autonomous-ai-organization` | Autonomous AI Organization | 1 / Urgent | Active | MastermindX |

Every row additionally has `owner = null`, `target_date = null`, `health = null`, `labels = []`, `parent_initiatives = []` at creation.

---

## Final Stop Condition

Do not claim this rollout complete because the strategy companion merged, tests are green, seven Initiative objects exist, or 50 membership writes returned success. Completion requires the Task-7 post-apply read-back to match the deterministic Project and Initiative desired state, the two exceptions to remain unassigned, no duplicate/multi-parent hierarchy to exist, and the durable Agent OS closeout to point a fresh session at the exact accepted evidence.
