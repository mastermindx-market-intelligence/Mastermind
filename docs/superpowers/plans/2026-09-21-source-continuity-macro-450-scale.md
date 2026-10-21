# Source Continuity Macro-450 Scale Implementation Plan

**Operation:** `source-continuity-macro-450-scale-successor-20260921-sol-001`
**Canonical owner:** Mastermind issue #346
**Protected pickup:** `4ca1b97e65de9d4ba8c868b9d708fb7620a8a76f`
**Predecessor:** PR #902 protected as the pickup commit above
**Capability ceiling:** source-only / evidence-only until normal review and release gates

## Goal

Extend the incumbent Source Continuity collision census from exactly 400 to exactly 450 open PRs
without changing any other resource envelope or any receipt, retry, persistence, transport,
lifecycle, authority, or release semantics.

The immediate live invalidator is the Macro estate: the START census observed 419 open Macro PRs,
above the protected 400 ceiling. This is a bounded current-estate capability slice, not a declaration
that 450 is permanent fleet scale.

## Closed profile

```text
max open PRs:              450
max logical HTTP calls:    1,152
max normalized bytes:      96 MiB
cooperative time:          300 s
per-response body cap:     5,000,000 bytes
```

Only the first value changes.
## Preserved semantics

Preserve protected #707 / #844 / #860 / #902 behavior unchanged:

- one invocation-wide call/byte/time budget spans the complete proof;
- open-roster and subject-PR semantic revalidation remain closed and fail-closed;
- relevant collision churn is re-proved under the incumbent collision owner;
- one safe default-branch fast-forward may be revalidated only under #902's exact contract;
- malformed, incomplete, colliding, identity-moving, budget-exhausted, or second-moving observations
  still refuse;
- no cache, retry loop, cursor, GraphQL/POST production path, second verifier, repository-specific
  profile, receipt schema, persistence, or new authority is introduced.

The 451st open PR must refuse `REMOTE_CENSUS_INCOMPLETE` before foreign-file enumeration.

## TDD evidence

The first modification was tests only. Against protected production code the new campaign produced:

```text
14 failed, 51 passed
```

The failures were exactly the stale 400 ceiling: exact profile mismatch; stable 409 / 410 / 419 /
425 / 450 estates refused; checkpoint and remote-complete 409 / 419 / 450 refused; the realistic
450-estate fanout could not enter foreign-file proof; and the closed-profile assertion remained 400.
## Live fanout model

The scale regression models the already-observed 17 large foreign PRs and 54 file pages beyond the
one-page-per-PR baseline:

- one 2,240-file PR: 23 pages, +22 extra;
- one 1,221-file PR: 13 pages, +12 extra;
- five 201-file PRs: 3 pages each, +10 extra;
- ten 101-file PRs: 2 pages each, +10 extra.

Both observations share the same 1,152-call ceiling. The incumbent verifier also reads one exact
page-30 saturation sentinel for each of the 17 large PRs on each observation. The realistic fanout
therefore adds exactly 142 logical reads over the 918-call 450-estate one-page baseline:
2 × (54 ordinary extra pages + 17 sentinels) = 142. Total = 1,060, leaving 92 calls of headroom.

## Scope

Exactly these paths are permitted:

1. `scripts/source_continuity.py`
2. `tests/test_source_continuity_macro_scale.py`
3. `tests/test_source_continuity_census_budget.py`
4. `tests/test_source_continuity_saturated_foreign_pr.py`
5. `tests/test_source_continuity_base_branch_semantics.py` — inherited 400→450 test-only pin
6. this plan

The production implementation is one semantic change:

```python
_MAX_COLLISION_PRS = 450
```
No other production definition should change.

## D8 / topology

Current protected D8 classifies identity/topology literals by semantic source context and excludes
Markdown plans from the generic source guard. `450` in `_MAX_COLLISION_PRS` is an estate
cardinality, not an identity. Do not weaken or bypass D8; run its real protected test on the final
diff and require an empty added-identity result.

## Completion boundary

Before source acceptance require:

1. focused 450-scale / census / saturated / #902 base-head suites green;
2. complete `tests/test_source_continuity*.py` family green;
3. exact call/byte/deadline one-unit-under discriminators green;
4. D8 topology/identity guard green;
5. compile + `git diff --check` + exact-five-path proof;
6. current protected integration proof if master moves;
7. one genuine non-author exact-head review;
8. canonical Source Continuity remote-complete;
9. a real held Macro consumer proof under the 450 profile;
10. terminal builder STOP / writer release / maintenance-only protected release.

A source merge remains `BUILT_NOT_PROVEN` until the real consumer proof owed by this successor is
accepted. It grants no merge, runtime, provider, deployment, product, or trading authority by itself.
