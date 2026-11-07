# Source Continuity Macro-485 Scale Implementation Plan

**Operation:** `source-continuity-macro-485-scale-successor-20260924-sol-001`
**Canonical owner:** Mastermind issue #346
**Protected pickup:** `1a7d400294b0d37c460b963b8865b40a23173b58`
**Protected predecessor:** PR #941 merge `0497e28864752e3ab70fa5aa2f1567bc3c9c6aca`
**Capability ceiling:** source-only / evidence-only until normal review and release gates

## Goal

Extend the incumbent Source Continuity collision census from exactly 475 to exactly 485 open PRs
without changing the 1,152-call, 128 MiB, 300-second, or 5,000,000-byte resource envelopes, and
without changing collision, receipt, retry, cache, persistence, transport, lifecycle, auth,
authority, or release semantics.

The action-time Macro estate is 478 open PRs, above the protected 475 ceiling. The protected adapter
must therefore refuse before the #6992 canary. This successor is a bounded current-estate capability
slice, not a permanent fleet-scale declaration.

## Independent bound review

A fresh read-only Sonnet review of protected `1a7d400…` returned `PASS_PROPOSE_485`.
Using the exact protected fixtures and the accepted adverse 17-large-PR / +54-extra-page shape:

- 478: 1,116 calls / 36 headroom;
- 480: 1,120 / 32;
- **485: 1,130 / 22**;
- 490: 1,140 / 12;
- 495: 1,150 / 2;
- 496: 1,152 / 0.

485 provides seven PRs of runway over the observed 478 estate while preserving 22 modeled calls of
headroom. 490 is materially tighter. 495/496 are rejected because one multi-page-PR surprise could
consume the remaining margin. Multi-page foreign PRs are the material nonlinear risk, so a real
read-only estate resource re-probe remains required before protection.

## Closed profile

```text
max open PRs:              485
max logical HTTP calls:    1,152
max normalized bytes:      128 MiB
cooperative time:          300 s
per-response body cap:     5,000,000 bytes
```

Only the first value may change from protected source.

## Preserved semantics

Preserve all protected Source Continuity behavior inherited through #941:

- one invocation-wide call/byte/time budget spans the complete proof;
- open-roster and subject-PR semantic revalidation remain fail-closed;
- relevant collision churn is re-proved under the incumbent collision owner;
- safe default-branch fast-forward behavior remains under its accepted contract;
- saturated foreign-PR tree proof and page-30 saturation sentinels remain unchanged;
- malformed, incomplete, colliding, identity-moving, budget-exhausted, or second-moving observations refuse;
- no cache, retry loop, cursor, GraphQL/POST production path, second verifier, repository-specific
  profile, receipt schema, persistence, auth widening, or new authority is introduced.

The 486th open PR must refuse `REMOTE_CENSUS_INCOMPLETE` before foreign-file enumeration.
Until this successor is protected, the current protected 475 profile continues to refuse at 476+.

## RED-first evidence required

Before the production edit, tests must fail because protected source still pins 475 while the successor contract requires:

- stable 476 / 477 / 478 / 479 / 480 / 481 / 482 / 483 / 484 / 485 estates to complete;
- 486 to refuse before foreign-file enumeration;
- the closed profile to report 485 with every other resource ceiling unchanged;
- realistic 485-estate adverse fanout to complete at exactly 1,130 calls with 22 calls of headroom;
- exact call/byte one-under discriminators to be derived from the 485 harness rather than copied from prose.

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
_MAX_COLLISION_PRS = 485
```

No other production definition changes.

## Completion boundary

Before source acceptance require:

1. RED evidence on protected 475 production after tests/plan land first;
2. focused Macro-scale / census / saturated / base-head suites green after the one-line production edit;
3. complete `tests/test_source_continuity*.py` family green;
4. exact call/byte/deadline one-unit-under discriminators green;
5. D8 topology/identity guard green;
6. compile + `git diff --check` + exact-six-path scope proof;
7. read-only live Macro estate resource study demonstrating the current estate fits the unchanged resource envelope;
8. current protected integration proof if master moves;
9. one genuine non-author exact-head review;
10. canonical Source Continuity remote-complete;
11. terminal builder STOP / writer release / maintenance-only protected release;
12. after protection, one real held Macro consumer proof using #6992 exact head
    `a51bae222eedd4c53f4101998f3a3c4bc103f554` and its original three-path operation contract.

A source merge remains `BUILT_NOT_PROVEN` until the real consumer proof is accepted. It grants no
runtime, provider, deployment, product, ranking, serving, or trading authority by itself.
