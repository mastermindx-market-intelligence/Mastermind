---
name: review-pull-request
description: Use when reviewing one exact GitHub pull request against its governing Mastermind outcome and current source law.
---

# Review Pull Request

Use for one exact GitHub pull request after recovering the governing outcome and source law.

## Mandatory current-source gate

Read protected Mastermind `master`, record its exact commit, load `docs/sol_skills/INDEX.md`, `REVIEW_RETURN.md`, and `RECONCILE_STATE.md` from that same exact commit, and verify compatibility. Run `bootstrap-mastermind` first. If compatibility cannot be established, modifying workflow is unavailable.

## Required package reference

Read `../../references/authority-boundaries.md` before interpreting any app, record, or action as authority. The reference summarizes canonical ownership; current protected source still controls.

## Procedure

1. Pin repository, PR number, base, exact immutable head, merge base, draft state, and current protected branch.
2. Obtain the complete changed-path census and exact diff. Detect overlapping open carriers before interpreting implementation.
3. Trace every changed unit to the accepted mission and explicit non-goals.
4. Review authority, identity, input and output schema, time, null, correction behavior, deterministic, statistical, and model-generated boundaries, failure states, effects, retries, credentials, logging, and no-duplicate-owner laws.
5. Read RED and GREEN evidence, focused tests, full relevant tests, hosted checks, security analysis, adversarial review, and production proof.
6. Falsify false completion: architecture is not implementation; implementation is not installed; installed is not production-proven.
7. Return `PASS`, `REQUEST_CHANGES`, or `BLOCKED_BY_CURRENT_SOURCE` with file and line or exact evidence.

## Output

```text
exact PR/head/base
changed-path census
mission coverage
major/minor findings
verification evidence
production proof state
verdict
exact repair or release gate
```

Do not merge from this skill. Merge and release remain a separate current-authority edge after a fresh exact-head and protected-source check.
