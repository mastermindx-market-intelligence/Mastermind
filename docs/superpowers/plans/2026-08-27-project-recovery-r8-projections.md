# Project Recovery R8-D/F — Linear Portfolio & Slack Visibility Projection Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Project accepted recovery state into the existing Linear portfolio and eventually `#build-events` without letting either projection become lifecycle truth, widening current app authority by accident, or creating a custom recovery relay.

**Architecture:** R8-D extends the existing one-way Agent OS → `linear_portfolio_plan.v1` → Mastermind Portfolio Projector path only after MAS-65/64/66 acceptance. Because current MAS-66 P1 explicitly does not manage labels/status, V1 recovery appears only inside the existing managed project-description block; the desired `CEO Recovery Required` label is held for a later explicit projector-authority widening. R8-F remains dependency-held because current official Linear/GitHub Slack integrations can only mirror their native event domains and do not consume `mastermind.project_recovery_assessment.v1`; no custom relay is authorized merely to force recovery alerts into Slack.

**Tech Stack:** Existing Macro `scripts/linear_portfolio_plan.py`, accepted MAS-66 project-only projector app, `mastermind.project_recovery_assessment.v1`, Linear/Slack official integrations only when their existing gates are accepted.

**Spec:** `docs/superpowers/specs/2026-08-27-project-recovery-sentinel-r8-design.md` plus current-state amendment.

## Global Constraints

- Current GitHub truth at planning: Macro PR #6182 / MAS-65 remains open/draft at exact head `298f70de89fc9c8d4606955e329afd074a9177e8`; do not assume the Linear description’s prepared merge happened.
- MAS-64 is `Todo / NOT_BUILT / Admin Prerequisite`; no dedicated Projector app actor/canary is proven.
- MAS-66 is `Todo / SPEC_ONLY`; its first accepted vertical manages project existence/name/summary/one marked managed description block/team binding/non-destructive active state only.
- MAS-66 explicitly does **not** manage labels, status updates, issues, gates, comments, milestones or initiatives in P1.
- Therefore R8-D V1 must not add/remove a `CEO Recovery Required` Linear label or mutate issue/project status under existing P1 authority.
- R8-D never creates one Linear issue per recovery finding.
- R8-D exact join is recovery `workstream` -> exact `WS:<KEY>` project projection; `PROGRAM:` orphan rows with no workstream are visible in Control Room/Agenda but are not fuzzy-created as Linear projects.
- MAS-103 and MAS-104 are currently `Todo / NOT_BUILT / Admin Prerequisite` official Slack visibility lanes.
- MAS-103 emits selected **issue** custom-view events; MAS-104 emits GitHub PR/review/workflow events. Neither is a recovery-assessment transport.
- No custom Slack webhook/relay/bot, cursor, transition database, retry queue or `#agent-dispatch` fallback is authorized by R8-F.
- Slack loss must lose no canonical recovery truth.

## Current gate ledger

| Gate | Current planning state | R8 consequence |
|---|---|---|
| MAS-65 report-only plan compiler | BUILT_NOT_PROVEN / PR #6182 still open | no R8-D compiler extension yet |
| MAS-64 Projector app actor | NOT_BUILT / Admin Prerequisite | no Linear mutation |
| MAS-66 project read/diff/apply | SPEC_ONLY | no managed-block apply |
| MAS-103 Linear → #build-events | NOT_BUILT | no Linear visibility assumptions |
| MAS-104 GitHub → #build-events | NOT_BUILT | no GitHub visibility assumptions |
| Recovery-specific Slack projection | NOT_BUILT / no accepted carrier | R8-F held; do not invent one |

---

## R8-D — Linear project projection

### Task 1: Reconcile projector authority before any code

**Files:**
- No modification in this task.

- [ ] **Step 1: Re-pin all three required gates**

At pickup, read current canonical truth for MAS-65, MAS-64 and MAS-66 plus Macro `main` and the accepted R8-A assessment contract.

Proceed only when:

```text
MAS-65 compiler = merged + Sol accepted
MAS-64 app actor = proven canary + exact app identity
MAS-66 project-only adapter = implemented + accepted dry-run mechanics
```

If MAS-66’s accepted authority still excludes labels/status, preserve the V1 managed-block-only design below.

- [ ] **Step 2: Confirm one-carrier path**

Identify the accepted file/module that produces `linear_portfolio_plan.v1` and the accepted MAS-66 consumer. If a newer projector replaced the names, update this plan to those exact owners; do not create `project_recovery_linear_sync.py` or a parallel projector.

- [ ] **Step 3: Stop if prerequisites are not accepted**

Record `R8_D_DEPENDENCY_HELD` with exact missing gate(s). This is the correct current outcome at planning time.

---

### Task 2: Extend the existing report-only Linear plan with an optional recovery snapshot

**Files after MAS-65 acceptance:**
- Modify the accepted Macro `scripts/linear_portfolio_plan.py`.
- Modify its accepted focused tests (`tests/linear_portfolio_plan_cases.py`, `tests/linear_portfolio_plan_live_cases.py` or their current successors).
- Add bounded fixture `research/linear_portfolio_p0/recovery_snapshot_fixture.json` only if the existing test convention uses witness fixtures; production current assessment remains external input, not committed mutable truth.

**Interfaces:**

Add an optional normalized input:

```python
recovery_assessment: Mapping[str, Any] | None
```

or CLI equivalent:

```text
--recovery-assessment /path/to/project_recovery_assessment.json
```

The plan row for an exact workstream adds:

```python
"recovery": {
    "available": True,
    "assessment_semantic_hash": "sha256:...",
    "disposition": "RECOVERY_REQUIRED",
    "finding_codes": ["ACTIVE_WITHOUT_CARRIER"],
    "next_ceo_action": "...",
}
```

and renders those fields inside the **existing** managed project-description block.

- [ ] **Step 1: Write RED exact-join tests**

```python
def test_recovery_joins_only_exact_ws_key(plan_fixture, recovery_fixture):
    recovery_fixture["subjects"] = [
        subject("WS:ALPHA", "RECOVERY_REQUIRED"),
        subject("WS:ALPHA-V2", "NO_RECOVERY_ACTION"),
    ]
    plan = compile_plan(..., recovery_assessment=recovery_fixture)
    alpha = row(plan, "WS:ALPHA")
    assert alpha["recovery"]["disposition"] == "RECOVERY_REQUIRED"
    assert row(plan, "WS:ALPHA-V2")["recovery"]["disposition"] == "NO_RECOVERY_ACTION"
```

- [ ] **Step 2: Write orphan/no-fuzzy-create test**

A recovery subject `PROGRAM:orphan-program` with no exact workstream does not create a new Linear plan project row. Emit a reconciliation warning such as `recovery_subject_unprojectable` with the subject id.

- [ ] **Step 3: Write unavailable-input test**

Missing assessment yields explicit `recovery_snapshot_unavailable` in the plan receipt and leaves existing portfolio desired state unchanged.

- [ ] **Step 4: Implement through the existing compiler only**

Validate exact assessment schema/hash, create an exact workstream index, and add a bounded recovery managed block subsection. Do not import Mastermind Python modules into Macro; consume the schema as normalized JSON just like other external witness snapshots.

- [ ] **Step 5: Run projector regressions**

Use the accepted MAS-65 focused + live-case test set. Same Agent OS + recovery inputs twice must produce byte-identical semantic plan output.

- [ ] **Step 6: Commit and return for independent review**

Commit as a separate post-MAS-65 extension PR. It remains report-only and performs no Linear mutation.

---

### Task 3: Freeze the managed recovery subsection; explicitly refuse labels/status

**Files:**
- Modify the accepted Linear plan renderer tests.

**Managed block addition:**

```text
Recovery
- disposition: RECOVERY_REQUIRED
- finding_codes: ACTIVE_WITHOUT_CARRIER
- assessment: sha256:<...>
- next CEO action: Reconcile the current frontier before commissioning another carrier.
```

- [ ] **Step 1: Write negative authorization tests**

Assert the desired-state plan contains no recovery-driven `labels`, `status`, `issue_create`, `issue_update` or project archive/delete mutation.

- [ ] **Step 2: Record label as an explicit future gate**

Machine/human receipt must state:

```text
CEO_RECOVERY_REQUIRED_LABEL = NOT_AUTHORIZED_CURRENT_P1
```

A later label projection requires a separate Sol-approved extension of the projector contract after MAS-66 acceptance; it is not smuggled into R8-D.

- [ ] **Step 3: Commit together with Task 2 or as one reviewer-sized follow-up**

---

### Task 4: Dry-run through the accepted MAS-66 adapter

**Files:**
- No new adapter files. Use the accepted MAS-66 implementation.

- [ ] **Step 1: Feed the extended `linear_portfolio_plan.v1` to MAS-66 in dry-run mode**

Require app actor identity proof from MAS-64. Record every exact `would_update|noop|remote_changed|managed_block_invalid` project outcome.

- [ ] **Step 2: Verify manual text preservation**

For a canary existing project, prove text outside `[MMX-PROJECTOR:BEGIN linear_portfolio_plan.v1]` / END remains byte/semantic-equivalent.

- [ ] **Step 3: Review current real portfolio dry-run**

No real apply occurs in this task. Sol reviews the diff, with special attention to recovery rows and projects lacking exact bindings.

---

### Task 5: First bounded real recovery projection after separate arming

- [ ] **Step 1: Obtain the existing projector’s separate real-apply arming decision**

MAS-66 completion does not itself authorize a portfolio-wide apply. R8-D cannot bypass that boundary.

- [ ] **Step 2: Apply to one exact existing workstream project first**

Choose one current `RECOVERY_REQUIRED` project with an exact Linear binding. Re-read immediately before apply; remote movement refuses mutation.

- [ ] **Step 3: Read back and verify**

Confirm app—not ChatGPT employee—attribution, exact managed recovery subsection, manual text preservation, and zero label/status/issue mutations.

- [ ] **Step 4: Expand only through the already-accepted projector arming scope**

No R8-specific scheduler is added. Continuous reconciliation remains a separate projector arming decision.

**R8-D stop condition:** the existing Linear project surface can show recovery state inside its managed block with exact app attribution and no authority widening. A visible `CEO Recovery Required` label is not part of V1 acceptance while current P1 forbids labels.

---

## R8-F — Slack transition visibility

### Task 6: Prove current official integrations cannot carry recovery transitions

**Files:**
- No product modification.

- [ ] **Step 1: Re-pin MAS-103 and MAS-104 after their admin canaries**

Confirm actual installed capabilities, not only runbooks.

- [ ] **Step 2: Evaluate exact event domains**

R8-F needs:

```text
assessment transition RECOVERY_REQUIRED entered/cleared
-> #build-events visibility message
```

Current MAS-103 domain is selected Linear **issue** view entry/terminal events. Current MAS-104 domain is GitHub PR/review/workflow events. Neither can accept a recovery-assessment transition directly.

- [ ] **Step 3: Reject invalid workarounds**

Do not:

- create one Linear issue per recovery item merely to trigger MAS-103;
- toggle issue status/labels as a transport surrogate;
- encode recovery as a fake GitHub PR/workflow event;
- use `#agent-dispatch`;
- build a custom Slack bot/webhook/relay merely for R8-F;
- store a transition cursor/database.

- [ ] **Step 4: Emit durable disposition**

Record:

```text
R8_F = DEPENDENCY_HELD
missing_capability = accepted regenerable non-authoritative recovery-assessment -> #build-events projection
```

This does not block R8-A/C/E or Linear R8-D.

---

### Task 7: Future recovery visibility adapter only after an accepted shared projection seam exists

This task is **not executable** until a separate current architecture supplies an approved generic visibility projection seam that is:

- regenerable from canonical current state;
- non-authoritative;
- write-only to `#build-events`;
- no queue/ACK/worker semantics;
- no cursor/retry DB;
- transition dedup/reconciliation owned by an already accepted visibility mechanism rather than R8 inventing one.

When that exists, the bounded R8 extension may map only:

```text
entered RECOVERY_REQUIRED -> CEO RECOVERY REQUIRED — <subject>
cleared RECOVERY_REQUIRED -> CEO RECOVERY CLEARED — <subject>
entered UNKNOWN_RECONCILE -> CEO RECOVERY UNKNOWN — <subject>
```

with assessment semantic hash + finding code, no raw source prose.

Until then, Control Room + Linear + Agenda are the permanent visibility surfaces and Slack is optional/degraded by design.

**R8-F stop condition:** dependency-held with exact reason is an accepted outcome. Do not block full recovery truth or create a second transport system to make Slack cosmetically complete.
