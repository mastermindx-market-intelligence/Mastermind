# Source Continuity Macro-490 Scale Implementation Plan

**Operation:** `source-continuity-macro-490-scale-successor-20260924-sol-001`
**Canonical owner:** Mastermind issue #346
**Protected pickup:** `a21370ef17f71beb51b798df218c4b5e4b01d3e0`
**Protected predecessor:** PR #965 merge `f1c070d733c4683b20bbbd9af8fae6c30dc38d84`
**Capability ceiling:** source-only / evidence-only until normal review and release gates

## Goal

Extend the incumbent protected Source Continuity collision census from exactly 485 to exactly 490 open PRs without changing the 1,152-call, 128 MiB, 300-second, or 5,000,000-byte resource envelopes, and without changing collision, receipt, retry, cache, persistence, transport, lifecycle, auth, authority, or release semantics.

The action-time Macro estate reached 486 open PRs. Protected 485 therefore correctly blocks the real high-churn #7797 canary required by the separate moving-collider successor #974. #974 is frozen at remote head `a4111eaa467095f132e728c848991687cf42cd16`; its local source lease was released before this successor STARTed. This scale slice is the sole active Source Continuity source writer.

## Bound evidence

A fresh read-only review of #974 rejected folding 485→490 into that PR because #974 explicitly freezes 485 and a six-path moving-collider scope. It required a dedicated scale successor.

Read-only fixture probes on exact #974 moving-collider code using the accepted adverse 17-large-PR / +54-extra-page shape and one moved collider with unchanged overlap projection measured:

- 486: 1,132 calls / 20 headroom;
- 488: 1,136 / 16;
- **490: 1,140 / 12**;
- 492: 1,144 / 8;
- 495: 1,150 / 2.

Normalized bytes remained below 1 MiB against the 128 MiB ceiling. 490 is the smallest deliberate ceiling that gives runway above the live 486 estate while retaining a nonzero modeled call margin. It is intentionally tighter than 485 and therefore requires its own exact-head review plus a fresh real-estate resource proof before protection. 491+ remains outside this successor and must fail closed.

## Closed profile

```text
max open PRs:              490
max logical HTTP calls:    1,152
max normalized bytes:      128 MiB
cooperative time:          300 s
per-response body cap:     5,000,000 bytes
```

Only the first value may change from protected source.

## Preserved semantics

Preserve all currently protected Source Continuity behavior:

- one invocation-wide call/byte/time budget spans the complete proof;
- open-roster and subject-PR semantic revalidation remain fail-closed;
- relevant collision churn remains under the incumbent protected collision owner;
- safe default-branch fast-forward behavior remains under its accepted contract;
- saturated foreign-PR tree proof and page-30 saturation sentinels remain unchanged;
- malformed, incomplete, colliding, identity-moving, budget-exhausted or second-moving observations keep their existing protected treatment;
- current receipt/writer-gate schemas and semantics remain unchanged;
- no cache, retry loop, cursor, GraphQL/POST production path, second verifier, repository-specific profile, persistence, auth widening, lifecycle or authority is introduced.

The 491st open PR must refuse `REMOTE_CENSUS_INCOMPLETE` before foreign-file enumeration. Until this successor protects, current protected 485 continues to refuse at 486+.

## RED-first evidence required

Before the production edit, tests must fail because protected source still pins 485 while the successor contract requires:

- stable 486 / 487 / 488 / 489 / 490 estates to complete;
- 491 to refuse before foreign-file enumeration;
- the closed profile to report 490 with every other resource ceiling unchanged;
- realistic adverse 490 fanout to complete at exactly 1,140 calls with 12 calls of headroom;
- exact call/byte one-under discriminators derived from the 490 harness rather than copied from prose.

After the one-line production edit, the same campaign must pass without weakening exact call, byte, deadline, saturated-PR, base-head, semantic-revalidation, receipt or authority tests.

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
_MAX_COLLISION_PRS = 490
```

No other production definition changes.

## Completion boundary

Before source acceptance require:

1. RED evidence on protected 485 production after tests/plan land first;
2. focused Macro-scale / census / saturated / base-head suites green after the one-line production edit;
3. complete `tests/test_source_continuity*.py` family green;
4. exact call/byte/deadline one-unit-under discriminators green;
5. D8 topology/identity guard green;
6. compile + `git diff --check` + exact-six-path scope proof;
7. fresh read-only live Macro resource study demonstrating the current estate fits the unchanged resource envelope;
8. current protected integration proof if master moves;
9. one genuine non-author exact-head review focused on the tighter 12-call margin;
10. canonical Source Continuity remote-complete;
11. terminal builder STOP / writer release / maintenance-only protected release.

After 490 protects, #974 must regain source custody on its same PR/branch, semantically recompose its moving-collider behavior on top of protected 490, obtain a new immutable review, and then run the real Macro #7797 canary. A 490 source merge alone grants no runtime, provider, deployment, product, ranking, serving or trading authority.
