# Project Workroom Convergence — Source-Provenance Amendment

**Date:** 2026-08-29  
**Owner:** Sol, AI CEO  
**Status:** `SPEC_ONLY / CHAIRMAN-APPROVED / RECORDS_ONLY`  
**Operation key:** `project-workroom-convergence-20260829-sol-001`  
**Carrier:** Mastermind PR #232 / `sol/project-workroom-convergence-20260829`  
**Current protected release basis:** `mastermindx-market-intelligence/Mastermind@1b99ea1d0a6232e11fd46915d348685764cb00cf`  
**Authority:** narrow precedence correction for WR-P0 strategy-source provenance. It supersedes the single-path `source_design` contract in the Workroom design, current-state amendment, planner-semantics amendment and implementation plan. It creates no Slack, Linear, runtime or credential mutation authority.

---

## 1. Records carrier file census

The exact PR #232 records-only carrier now contains five files:

```text
docs/superpowers/specs/2026-08-29-project-workroom-convergence-design.md
docs/superpowers/specs/2026-08-29-project-workroom-convergence-current-state-amendment.md
docs/superpowers/specs/2026-08-29-project-workroom-convergence-planner-semantics-amendment.md
docs/superpowers/specs/2026-08-29-project-workroom-convergence-source-provenance-amendment.md
docs/superpowers/plans/2026-08-29-project-workroom-convergence.md
```

No runtime, config, test, Agent OS, Linear, Slack, credential or production path is modified by this records carrier.

---

## 2. One source path is insufficient

The original WR-P0 strategy shape used:

```text
source_design
  repository
  path
  protected_revision
```

That became incomplete after the current-state and planner-semantics amendments gained narrow precedence. A future cold start following only the base design path could miss controlling Initiative, portfolio-plan, shadow/apply and action-emission law even though the revision itself contained those files.

The strategy must therefore name the complete governing source set explicitly.

---

## 3. Correct strategy source contract

Replace top-level `source_design` with:

```text
source_records
  repository
  protected_revision
  paths[]
```

Exact values:

```text
repository = mastermindx-market-intelligence/Mastermind
protected_revision = exact protected merge SHA of PR #232
paths =
  docs/superpowers/specs/2026-08-29-project-workroom-convergence-design.md
  docs/superpowers/specs/2026-08-29-project-workroom-convergence-current-state-amendment.md
  docs/superpowers/specs/2026-08-29-project-workroom-convergence-planner-semantics-amendment.md
  docs/superpowers/specs/2026-08-29-project-workroom-convergence-source-provenance-amendment.md
```

`paths` is sorted, duplicate-free and exact. The implementation plan path is not strategy/source-law authority and is therefore not included in `source_records.paths`; it remains the execution DAG referenced by the protected records carrier.

The strategy carries paths, not file contents or content digests. The one protected merge SHA supplies immutable atomic provenance for all four files.

---

## 4. Validation and refusal behavior

WR-P0 strategy validation must require exactly:

```text
schema
source_records
workspace_id
channel_prefix
workrooms
```

`source_records` must contain exactly:

```text
repository
protected_revision
paths
```

Required refusal codes include:

```text
strategy_source_records_invalid
strategy_source_repository_mismatch
strategy_source_revision_invalid
strategy_source_paths_mismatch
strategy_source_paths_duplicate
```

The old key `source_design`, a missing amendment path, an extra path, duplicate path, wrong repository or non-40-hex protected revision causes a hard strategy refusal.

No fuzzy filename, directory scan or newest-amendment selection is allowed.

---

## 5. Tests and config correction

`config/project_workroom_strategy.v1.json` must use `source_records` and the four exact paths above.

RED-first tests must prove:

```text
all four source paths are present at one protected SHA
old source_design key is refused
missing current-state amendment is refused
missing planner-semantics amendment is refused
missing provenance amendment is refused
extra source path is refused
duplicate source path is refused
wrong repository is refused
invalid protected revision is refused
```

The strategy digest and every downstream desired-source digest naturally change when the complete source record changes.

---

## 6. No other change

All other Workroom hierarchy, Initiative mapping, Agent OS portfolio-plan input, shadow/apply separation, action semantics, Sol Project Steward model, operator isolation, Slack principal split, Canvas/List/workflow law, one-carrier/effect-unknown behavior, security boundaries, rollout stages, failure matrix and acceptance canaries remain unchanged.

This amendment does not make WR-P0 protected, create a live Workroom, or authorize any actuator.