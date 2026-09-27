# Source Continuity Macro-475 Scale Implementation Plan

**Operation:** `source-continuity-macro-475-scale-successor-20260923-sol-001`
**Canonical owner:** Mastermind issue #346
**Protected pickup:** `009488c17f07f610549f45f34c9dbaecb8618f14`
**Predecessor:** PR #938 protected as the pickup commit above
**Capability ceiling:** source-only / evidence-only until normal review and release gates

## Goal

Extend the incumbent Source Continuity collision census from exactly 450 to exactly 475 open PRs
without changing the 1,152-call, 128 MiB, 300-second, or 5,000,000-byte resource envelopes, and
without changing receipt, retry, persistence, transport, lifecycle, authority, or release semantics.

The live invalidator is the Macro estate at 458 open PRs, above the protected 450 ceiling. This is a
bounded current-estate capability slice, not a declaration that 475 is permanent fleet scale.

## Closed profile

```text
max open PRs:              475
max logical HTTP calls:    1,152
max normalized bytes:      128 MiB
cooperative time:          300 s
per-response body cap:     5,000,000 bytes
```

Only the first value changes from protected #938.

## Why 475

A hermetic exact-#938 study preserved all non-cardinality bounds and modeled the already-accepted
17-large-PR / +54-ordinary-page foreign-file shape:

- 457 open PRs: 1,074 calls / 78 headroom;
- 465: 1,090 / 62;
- 470: 1,100 / 52;
- 475: 1,110 / 42;
- 480: 1,120 / 32.

The prior 500 proposal was rejected because its projected call headroom was too narrow. 475 preserves
a bounded 42-call margin in the same adverse fanout model while admitting the current >450 estate.

A read-only live study against the current Macro estate, using exact #938 code with only the
cardinality ceiling changed in memory to 475, completed the remote census at 675 GETs,
109,026,023 normalized bytes (103.975 MiB), and 170.154 seconds before a later local
`OUT_OF_SCOPE_DIRT` refusal caused by ignored pytest/bytecode residue. The remote proof therefore
fits the inherited 1,152-call / 128-MiB / 300-second envelope without widening it.

## Preserved semantics

Preserve all protected Source Continuity behavior from #707 / #844 / #860 / #902 / #907 / #938:

- one invocation-wide call/byte/time budget spans the complete proof;
- open-roster and subject-PR semantic revalidation remain fail-closed;
- relevant collision churn is re-proved under the incumbent collision owner;
- safe default-branch fast-forward behavior remains under #902's exact contract;
- saturated foreign-PR tree proof and page-30 saturation sentinels remain unchanged;
- malformed, incomplete, colliding, identity-moving, budget-exhausted, or second-moving observations refuse;
- no cache, retry loop, cursor, GraphQL/POST production path, second verifier, repository-specific
  profile, receipt schema, persistence, or new authority is introduced.

The 476th open PR must refuse `REMOTE_CENSUS_INCOMPLETE` before foreign-file enumeration.

## TDD evidence required

Before the production edit, tests must fail because protected source still pins 450 while the new contract requires:

- stable 451 / 457 / 458 / 465 / 470 / 475 estates to complete;
- 476 to refuse before foreign-file enumeration;
- the closed profile to report 475 with all other resource ceilings unchanged;
- realistic 475-estate fanout to complete at exactly 1,110 calls with 42 calls of headroom.

After the one-line production edit, the same campaign must pass without weakening exact call, byte,
deadline, saturated-PR, base-head, semantic-revalidation, or authority tests.

## Exact source scope

Exactly these paths are permitted:

1. `scripts/source_continuity.py`
2. `tests/test_source_continuity_macro_scale.py`
3. `tests/test_source_continuity_census_budget.py`
4. `tests/test_source_continuity_saturated_foreign_pr.py`
5. `tests/test_source_continuity_base_branch_semantics.py`
6. this plan

The production implementation is one semantic change:

```python
_MAX_COLLISION_PRS = 475
```

No other production definition changes.

## D8 / topology

The 475 literal is an estate cardinality, not an identity. Do not weaken or bypass D8. Require the
real protected topology/identity guard to report no forbidden added production identity on the final diff.

## Completion boundary

Before source acceptance require:

1. focused Macro-scale / census / saturated / base-head suites green;
2. complete `tests/test_source_continuity*.py` family green;
3. exact call/byte/deadline one-unit-under discriminators green;
4. D8 topology/identity guard green;
5. compile + `git diff --check` + exact-six-path scope proof;
6. current protected integration proof if master moves;
7. one genuine non-author exact-head review;
8. canonical Source Continuity remote-complete;
9. terminal builder STOP / writer release / maintenance-only protected release;
10. after protection, one real held Macro consumer proof using #6992 exact head
   `a51bae222eedd4c53f4101998f3a3c4bc103f554` and its original three-path operation contract.

A source merge remains `BUILT_NOT_PROVEN` until the real consumer proof is accepted. It grants no
runtime, provider, deployment, product, ranking, serving, or trading authority by itself.
